"""Public research projections over the existing read-only source snapshot.

Event-date location inheritance is shared with Operations. The public status gate
applies before counts, search, relations and exports, including date overrides.
"""

from dataclasses import replace
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.errors import APIError
from app.repositories.activity_previews import image_url, location
from app.repositories.created_period import require_timezone
from app.repositories.entities import pagination
from app.repositories.entity_search import SEARCH_DEFINITIONS, escape_search
from app.repositories.location import EFFECTIVE_SPACE_SQL, EFFECTIVE_VENUE_SQL
from app.schemas.research import (
    ResearchCategory,
    ResearchDate,
    ResearchDates,
    ResearchDetail,
    ResearchExport,
    ResearchFilters,
    ResearchMonth,
    ResearchOptions,
    ResearchPage,
    ResearchRecord,
    ResearchType,
    ResearchUsageItem,
)
from app.services.quality.urls import url_problem

PUBLIC = "('released','cancelled','deferred','rescheduled')"
DATE_STATUS = "COALESCE(NULLIF(d.release_status::text,'inherited'),e.release_status::text)"
CATEGORY_LABELS = """SELECT DISTINCT ON (category_id) category_id,name
    FROM uranus.event_category WHERE NULLIF(trim(name),'') IS NOT NULL
    ORDER BY category_id,CASE iso_639_1 WHEN 'de' THEN 0 WHEN 'en' THEN 1 ELSE 2 END,
        iso_639_1 COLLATE "C" NULLS LAST,name COLLATE "C"
"""
CATEGORIES = """COALESCE((SELECT jsonb_agg(jsonb_build_object('id',c.id,'name',
    COALESCE(l.name,'Kategorie '||c.id)) ORDER BY c.id)
    FROM (SELECT DISTINCT unnest(e.categories) id) c
    LEFT JOIN category_labels l ON l.category_id=c.id WHERE c.id IS NOT NULL),'[]'::jsonb)"""
ADDRESS = """NULLIF(concat_ws(', ',
    NULLIF(concat_ws(' ',NULLIF(v.street,''),NULLIF(v.house_number,'')),''),
    NULLIF(concat_ws(' ',NULLIF(v.postal_code,''),NULLIF(v.city,'')),'')),'')"""
DATE_COLUMNS = f"""d.uuid id,d.event_uuid,d.start_date,d.start_time,d.end_date,d.end_time,d.all_day,
    {DATE_STATUS} status,v.uuid venue_id,v.name venue_name,s.uuid space_id,s.name space_name,
    v.city,{ADDRESS} address,public.ST_Y(v.point) latitude,public.ST_X(v.point) longitude"""
DATE_JOINS = f"""FROM uranus.event_date d JOIN uranus.event e ON e.uuid=d.event_uuid
    LEFT JOIN uranus.venue v ON v.uuid={EFFECTIVE_VENUE_SQL}
    LEFT JOIN uranus.space s ON s.uuid={EFFECTIVE_SPACE_SQL}"""
DATE_FILTER = f"""e.release_status::text IN {PUBLIC} AND {DATE_STATUS} IN {PUBLIC}
    AND (CAST(:from_date AS date) IS NULL OR d.start_date>=:from_date)
    AND (CAST(:to_date AS date) IS NULL OR d.start_date<=:to_date)
    AND (:city='' OR v.city ILIKE :city)
    AND (CAST(:venue_id AS uuid) IS NULL OR v.uuid=:venue_id)
    AND (CAST(:status AS text) IS NULL OR {DATE_STATUS}=:status)"""
# Search uses the canonical definitions, with privacy-sensitive fields removed.
# Private contact/external IDs must not become a search-based existence oracle.
SEARCH_FIELDS = {
    "uuid",
    "name",
    "title",
    "subtitle",
    "street",
    "house_number",
    "postal_code",
    "city",
}


def search_sql(kind: ResearchType) -> str:
    definition = SEARCH_DEFINITIONS[kind]
    fields = [
        (sql, name)
        for sql, name in zip(definition.fields, definition.field_names, strict=True)
        if name in SEARCH_FIELDS
    ]
    public = replace(
        definition,
        fields=tuple(sql for sql, _ in fields),
        field_names=tuple(name for _, name in fields),
        subtitle="NULL::text",
    )
    return f"SELECT entity_key FROM ({public.projection()}) search WHERE {public.matches()}"


def parameters(filters: ResearchFilters, settings: Settings) -> dict[str, Any]:
    return {
        **filters.model_dump(),
        "q": f"%{escape_search(filters.q)}%",
        "city": f"%{escape_search(filters.city)}%" if filters.city.strip() else "",
        "tz": require_timezone(settings),
        "offset": (filters.page - 1) * filters.page_size,
        "key": None,
    }


def research_sql() -> str:
    branches = []
    for kind, alias, table in (("venue", "v", "venue"), ("organization", "v", "organization")):
        link = "m.venue_id=v.uuid" if kind == "venue" else "m.organization_id=v.uuid"
        branches.append(f"""SELECT '{kind}'::text entity_type,v.uuid entity_key,v.name,
            v.description,NULL::text status,'[]'::jsonb categories,v.content_iso_639_1 language,
            NULL::date start_date,NULL::time start_time,NULL::date end_date,NULL::time end_time,
            NULL::boolean all_day,NULL::uuid organization_id,NULL::text organization_name,
            NULL::uuid venue_id,NULL::text venue_name,NULL::uuid space_id,NULL::text space_name,
            v.city,{ADDRESS} address,public.ST_Y(v.point) latitude,public.ST_X(v.point) longitude,
            (SELECT count(DISTINCT m.entity_key) FROM matched_events m WHERE {link}) event_count,
            v.web_link source_url,v.created_at AT TIME ZONE :tz created_at,
            v.modified_at AT TIME ZONE :tz modified_at
            FROM uranus.{table} {alias} WHERE EXISTS (
                SELECT 1 FROM matched_events m WHERE {link})""")
    return f"""WITH category_labels AS ({CATEGORY_LABELS}),
    filtered_dates AS MATERIALIZED (SELECT {DATE_COLUMNS} {DATE_JOINS} WHERE {DATE_FILTER}),
    matched_events AS MATERIALIZED (
        SELECT 'event'::text entity_type,e.uuid entity_key,d.id date_key,e.title name,e.description,
        COALESCE(d.status,e.release_status::text) status,{CATEGORIES} categories,
        e.content_iso_639_1 language,d.start_date,d.start_time,d.end_date,d.end_time,d.all_day,
        o.uuid organization_id,o.name organization_name,d.venue_id,d.venue_name,
        d.space_id,d.space_name,d.city,d.address,d.latitude,d.longitude,
        NULL::bigint event_count,e.source_link source_url,
        e.created_at AT TIME ZONE :tz created_at,e.modified_at AT TIME ZONE :tz modified_at
        FROM uranus.event e JOIN uranus.organization o ON o.uuid=e.org_uuid
        LEFT JOIN filtered_dates d ON d.event_uuid=e.uuid
        WHERE e.release_status::text IN {PUBLIC}
        AND (CAST(:organization_id AS uuid) IS NULL OR e.org_uuid=:organization_id)
        AND (CAST(:category AS integer) IS NULL OR :category=ANY(e.categories))
        AND (d.id IS NOT NULL OR (
            NOT EXISTS (SELECT 1 FROM uranus.event_date known WHERE known.event_uuid=e.uuid)
            AND CAST(:from_date AS date) IS NULL AND CAST(:to_date AS date) IS NULL
            AND :city='' AND CAST(:venue_id AS uuid) IS NULL
            AND (CAST(:status AS text) IS NULL OR e.release_status::text=:status)))
    ), event_records AS (
        SELECT DISTINCT ON (entity_key) entity_type,entity_key,name,description,status,categories,
            language,start_date,start_time,end_date,end_time,all_day,organization_id,organization_name,
            venue_id,venue_name,space_id,space_name,city,address,latitude,longitude,event_count,
            source_url,created_at,modified_at FROM matched_events
        ORDER BY entity_key,start_date NULLS LAST,start_time NULLS LAST,date_key
    ), records AS (SELECT * FROM event_records UNION ALL {" UNION ALL ".join(branches)})
    SELECT entity_type,entity_key,name,description,status,categories,language,start_date,start_time,
        end_date,end_time,all_day,organization_id,organization_name,venue_id,venue_name,space_id,
        space_name,city,address,latitude,longitude,event_count,source_url,created_at,modified_at
    FROM records WHERE (:entity_type='all' OR entity_type=:entity_type)
    AND (CAST(:key AS uuid) IS NULL OR entity_key=:key)
    AND ( :q='%%' OR
        (entity_type='event' AND entity_key::text IN ({search_sql("event")})) OR
        (entity_type='venue' AND entity_key::text IN ({search_sql("venue")})) OR
        (entity_type='organization' AND entity_key::text IN ({search_sql("organization")})))"""


ORDER = {
    "date": (
        'start_date NULLS LAST,start_time NULLS LAST,lower(name) COLLATE "C",entity_type,entity_key'
    ),
    "name": 'lower(name) COLLATE "C",entity_type,entity_key',
}


def source_url(value: str | None) -> str | None:
    if not value or not value.strip() or len(value) > 2048 or url_problem(value) is not None:
        return None
    parsed = urlsplit(value)
    # Source links are optional public references, never credential-bearing URLs.
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None
    return value.strip()


def record(row: Any) -> ResearchRecord:
    return ResearchRecord.model_validate(
        {
            **dict(row),
            "location": location(row["latitude"], row["longitude"]),
            "source_url": source_url(row["source_url"]),
        }
    )


async def images(
    connection: AsyncConnection, items: list[ResearchRecord], settings: Settings
) -> None:
    if not items:
        return
    rows = (
        await connection.execute(
            text("""SELECT DISTINCT ON (l.context,l.context_uuid)
        l.context,l.context_uuid,i.uuid FROM uranus.pluto_image_link l
        JOIN uranus.pluto_image i ON i.uuid=l.pluto_image_uuid
        JOIN unnest(CAST(:kinds AS text[]),CAST(:ids AS uuid[])) r(kind,id)
            ON r.kind=l.context AND r.id=l.context_uuid
        WHERE (l.context='event' AND l.identifier='main')
        OR (l.context='organization' AND l.identifier='main_logo')
        OR (l.context='venue' AND l.identifier IN ('main_photo','main_logo'))
        ORDER BY l.context,l.context_uuid,
            CASE WHEN l.identifier='main_photo' THEN 0 ELSE 1 END,l.identifier,i.uuid"""),
            {"kinds": [i.entity_type for i in items], "ids": [i.entity_key for i in items]},
        )
    ).mappings()
    urls = {
        (r["context"], r["context_uuid"]): image_url(r["uuid"], settings.uranus_api_url)
        for r in rows
    }
    for item in items:
        item.image_url = urls.get((item.entity_type, item.entity_key))


async def research_page(
    connection: AsyncConnection, settings: Settings, filters: ResearchFilters, now: datetime
) -> ResearchPage:
    sql, params = research_sql(), parameters(filters, settings)
    total = int(
        (await connection.execute(text(f"SELECT count(*) FROM ({sql}) r"), params)).scalar_one()
    )
    rows = (
        await connection.execute(
            text(f"{sql} ORDER BY {ORDER[filters.sort]} LIMIT :page_size OFFSET :offset"), params
        )
    ).mappings()
    items = [record(row) for row in rows]
    await images(connection, items, settings)
    return ResearchPage(
        items=items,
        pagination=pagination(filters.page, filters.page_size, total),
        observed_at=now,
        timezone=settings.event_timezone,
    )


async def research_detail(
    connection: AsyncConnection,
    settings: Settings,
    kind: ResearchType,
    key: UUID,
    filters: ResearchFilters,
    now: datetime,
) -> ResearchDetail:
    params = parameters(ResearchFilters(entity_type=kind), settings)
    params["key"] = key
    row = (await connection.execute(text(research_sql()), params)).mappings().one_or_none()
    if row is None:
        raise APIError(404, "record_not_found", "Record not found.")
    item = record(row)
    if kind == "event":
        # Dossier overview describes the event; individual dates retain their overrides.
        status = (
            await connection.execute(
                text("SELECT release_status::text FROM uranus.event WHERE uuid=:key"), {"key": key}
            )
        ).scalar_one()
        item = ResearchRecord.model_validate({**item.model_dump(), "status": status})
    await images(connection, [item], settings)
    event_filters = filters.model_copy(update={"entity_type": "event"})
    if kind == "organization":
        event_filters.organization_id = key
    elif kind == "venue":
        event_filters.venue_id = key
    events = ResearchPage(
        items=[], pagination=pagination(1, 25, 0), observed_at=now, timezone=settings.event_timezone
    )
    dates = ResearchDates(items=[], pagination=pagination(filters.page, filters.page_size, 0))
    months: list[ResearchMonth] = []
    usage: list[ResearchUsageItem] = []
    if kind == "event":
        params = parameters(filters, settings)
        params["key"] = key
        predicate = f"""{DATE_FILTER} AND e.uuid=:key
            AND (CAST(:organization_id AS uuid) IS NULL OR e.org_uuid=:organization_id)
            AND (CAST(:category AS integer) IS NULL OR :category=ANY(e.categories))
            AND (:q='%%' OR e.uuid::text IN ({search_sql("event")}))"""
        total = int(
            (
                await connection.execute(
                    text(f"SELECT count(*) {DATE_JOINS} WHERE {predicate}"), params
                )
            ).scalar_one()
        )
        rows = (
            await connection.execute(
                text(
                    f"SELECT {DATE_COLUMNS} {DATE_JOINS} WHERE {predicate} "
                    "ORDER BY d.start_date,d.start_time NULLS LAST,d.uuid "
                    "LIMIT :page_size OFFSET :offset"
                ),
                params,
            )
        ).mappings()
        dates = ResearchDates(
            items=[
                ResearchDate.model_validate(
                    {**dict(r), "location": location(r["latitude"], r["longitude"])}
                )
                for r in rows
            ],
            pagination=pagination(filters.page, filters.page_size, total),
        )
    else:
        events = await research_page(connection, settings, event_filters, now)
        params = parameters(event_filters, settings)
        # A bounded monthly series counts distinct events in each calendar month.
        rows = (
            await connection.execute(
                text(f"""SELECT date_trunc('month',d.start_date)::date AS month,
            count(DISTINCT e.uuid) event_count {DATE_JOINS} WHERE {DATE_FILTER}
            AND (CAST(:organization_id AS uuid) IS NULL OR e.org_uuid=:organization_id)
            AND (CAST(:category AS integer) IS NULL OR :category=ANY(e.categories))
            AND (:q='%%' OR e.uuid::text IN ({search_sql("event")}))
            GROUP BY 1 ORDER BY 1 DESC LIMIT 120"""),
                params,
            )
        ).mappings()
        months = [ResearchMonth.model_validate(r) for r in rows]
        usage_rows = (
            await connection.execute(
                text(f"""
            WITH category_labels AS ({CATEGORY_LABELS}), occurrences AS MATERIALIZED (
                SELECT e.uuid event_id,e.org_uuid,o.name organization_name,
                    v.uuid venue_id,v.name venue_name,e.categories
                {DATE_JOINS} JOIN uranus.organization o ON o.uuid=e.org_uuid
                WHERE {DATE_FILTER}
                AND (CAST(:organization_id AS uuid) IS NULL OR e.org_uuid=:organization_id)
                AND (CAST(:category AS integer) IS NULL OR :category=ANY(e.categories))
                AND (:q='%%' OR e.uuid::text IN ({search_sql("event")}))
            ), usage AS (
                SELECT 'venue' kind,venue_id::text key,venue_name name,
                    count(DISTINCT event_id) event_count FROM occurrences
                WHERE venue_id IS NOT NULL GROUP BY venue_id,venue_name
                UNION ALL
                SELECT 'organization',org_uuid::text,organization_name,
                    count(DISTINCT event_id) FROM occurrences GROUP BY org_uuid,organization_name
                UNION ALL
                SELECT 'category',c.id::text,COALESCE(l.name,'Kategorie '||c.id),
                    count(DISTINCT event_id) FROM occurrences
                CROSS JOIN LATERAL unnest(categories) c(id)
                LEFT JOIN category_labels l ON l.category_id=c.id
                WHERE c.id IS NOT NULL GROUP BY c.id,l.name
            ), ranked AS (
                SELECT kind,key,name,event_count,row_number() OVER (PARTITION BY kind
                    ORDER BY event_count DESC,name COLLATE "C",key COLLATE "C") rank FROM usage
            ) SELECT kind,key,name,event_count FROM ranked WHERE rank<=10 ORDER BY kind,rank
        """),
                params,
            )
        ).mappings()
        usage = [ResearchUsageItem.model_validate(r) for r in usage_rows]
    return ResearchDetail(
        item=item, events=events, dates=dates, months=months, usage=usage, observed_at=now
    )


async def research_export(
    connection: AsyncConnection, settings: Settings, filters: ResearchFilters, now: datetime
) -> ResearchExport:
    sql, params = research_sql(), parameters(filters, settings)
    rows = (
        (
            await connection.execute(
                text(f"{sql} ORDER BY {ORDER[filters.sort]} LIMIT 10001"), params
            )
        )
        .mappings()
        .all()
    )
    if len(rows) > 10000:
        raise APIError(
            422, "research_export_limit", "Narrow the selection to at most 10000 records."
        )
    columns = [
        "entity_type",
        "event_uuid",
        "entity_uuid",
        "title",
        "start_date",
        "start_time",
        "organization",
        "venue",
        "city",
        "status",
        "source_url",
    ]
    exported = []
    for row in rows:
        item = record(row)
        exported.append(
            dict(
                zip(
                    columns,
                    [
                        item.entity_type,
                        str(item.entity_key) if item.entity_type == "event" else None,
                        str(item.entity_key),
                        item.name,
                        str(item.start_date) if item.start_date else None,
                        str(item.start_time) if item.start_time else None,
                        item.organization_name,
                        item.venue_name,
                        item.city,
                        item.status,
                        item.source_url,
                    ],
                    strict=True,
                )
            )
        )
    return ResearchExport(columns=columns, rows=exported, total=len(rows), observed_at=now)


async def research_options(connection: AsyncConnection) -> ResearchOptions:
    rows = (
        await connection.execute(
            text(f"""WITH labels AS ({CATEGORY_LABELS})
        SELECT DISTINCT c.id,COALESCE(l.name,'Kategorie '||c.id) name
        FROM uranus.event e CROSS JOIN LATERAL unnest(e.categories) c(id)
        LEFT JOIN labels l ON l.category_id=c.id
        WHERE e.release_status::text IN {PUBLIC} AND c.id IS NOT NULL
        ORDER BY c.id LIMIT 1000""")
        )
    ).mappings()
    return ResearchOptions(categories=[ResearchCategory.model_validate(r) for r in rows])
