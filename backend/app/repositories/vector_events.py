"""Bounded public event snapshot. No model calls or source mutations in this module."""

import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Literal, overload
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.repositories.activity_previews import location
from app.repositories.location import EFFECTIVE_SPACE_SQL, EFFECTIVE_VENUE_SQL
from app.repositories.research import CATEGORY_LABELS, DATE_STATUS, PUBLIC
from app.repositories.temporal import is_upcoming_start
from app.research.semantic_contracts import EffectiveLocation, SemanticDocument
from app.research.semantic_documents import event_document, public_clean
from app.research.vector_documents import EventDocument, document

PUBLIC_EVENT = f"""e.release_status::text IN {PUBLIC} AND (
    NOT EXISTS(SELECT 1 FROM uranus.event_date d WHERE d.event_uuid=e.uuid)
    OR EXISTS(SELECT 1 FROM uranus.event_date d WHERE d.event_uuid=e.uuid
        AND {DATE_STATUS} IN {PUBLIC}))"""
EVENT_SQL = f"""WITH category_labels AS ({CATEGORY_LABELS})
SELECT e.uuid entity_id,e.title,e.subtitle,e.summary,e.description,
    e.org_uuid organization_id,o.name organization_name,e.release_status::text status,
    e.content_iso_639_1 language,e.languages,e.tags,e.categories category_ids,
    e.participation_info,e.meeting_point,e.min_age,e.max_age,
    e.online_link,e.source_link,e.ticket_link,e.ticket_flags::text[] ticket_flags,
    e.price_type::text price_type,e.currency,e.min_price,e.max_price,
    e.registration_link,e.registration_deadline,
    e.modified_at AT TIME ZONE :source_tz source_updated_at,
    ARRAY(SELECT c.name FROM category_labels c WHERE c.category_id=ANY(e.categories)
        ORDER BY c.category_id) category_names
FROM uranus.event e JOIN uranus.organization o ON o.uuid=e.org_uuid
WHERE {PUBLIC_EVENT} ORDER BY e.uuid LIMIT :limit"""
DATES_SQL = f"""SELECT d.event_uuid,d.start_date,d.start_time,d.end_date,d.end_time,d.all_day,
    v.uuid venue_id,v.name venue_name,s.uuid space_id,s.name space_name,
    ST_X(v.point) longitude,ST_Y(v.point) latitude,
    v.accessibility_summary venue_accessibility,s.accessibility_summary space_accessibility,
    d.accessibility_info date_accessibility
FROM uranus.event_date d JOIN uranus.event e ON e.uuid=d.event_uuid
LEFT JOIN uranus.venue v ON v.uuid={EFFECTIVE_VENUE_SQL}
LEFT JOIN uranus.space s ON s.uuid={EFFECTIVE_SPACE_SQL}
WHERE e.uuid=ANY(CAST(:ids AS uuid[])) AND e.release_status::text IN {PUBLIC}
    AND {DATE_STATUS} IN {PUBLIC}
ORDER BY d.event_uuid,d.start_date,d.start_time NULLS LAST,d.uuid LIMIT 100001"""
TYPES_SQL = """WITH types AS (
    SELECT DISTINCT ON(type_id) type_id,name FROM uranus.event_type
    WHERE NULLIF(trim(name),'') IS NOT NULL
    ORDER BY type_id,CASE iso_639_1 WHEN 'de' THEN 0 WHEN 'en' THEN 1 ELSE 2 END,
        iso_639_1 COLLATE "C" NULLS LAST,name COLLATE "C"
), genres AS (
    SELECT DISTINCT ON(type_id,genre_id) type_id,genre_id,name FROM uranus.genre_type
    WHERE NULLIF(trim(name),'') IS NOT NULL
    ORDER BY type_id,genre_id,CASE iso_639_1 WHEN 'de' THEN 0 WHEN 'en' THEN 1 ELSE 2 END,
        iso_639_1 COLLATE "C" NULLS LAST,name COLLATE "C"
) SELECT l.event_uuid,l.type_id,l.genre_id,t.name type_name,g.name genre_name
FROM uranus.event_type_link l LEFT JOIN types t ON t.type_id=l.type_id
LEFT JOIN genres g ON g.type_id=l.type_id AND g.genre_id=l.genre_id AND l.genre_id<>0
WHERE l.event_uuid=ANY(CAST(:ids AS uuid[]))
ORDER BY l.event_uuid,l.type_id,l.genre_id LIMIT 100001"""


async def area_memberships(
    admin: AsyncConnection | None,
    dates: list[dict[str, Any]],
) -> tuple[bool, dict[str, list[dict[str, str]]]]:
    if admin is None:
        return False, {}
    exists = (
        await admin.execute(text("SELECT to_regclass('admin.research_area') IS NOT NULL"))
    ).scalar_one()
    if not exists:
        return False, {}
    points = {
        str(d["venue_id"]): {"id": str(d["venue_id"]), "x": d["longitude"], "y": d["latitude"]}
        for d in dates
        if d["venue_id"] and location(d["latitude"], d["longitude"]) is not None
    }
    # Imports already reject positive-area overlaps. Fail closed if cached geometry
    # was corrupted; shared edges remain valid and ST_Covers includes both sides.
    if (
        await admin.execute(
            text("""SELECT EXISTS (
        SELECT 1 FROM admin.research_area a JOIN admin.research_area b
        ON a.id<b.id AND a.geometry && b.geometry
        WHERE a.area_type='municipality' AND b.area_type='municipality'
        AND ST_Relate(a.geometry,b.geometry,'2********'))""")
        )
    ).scalar_one():
        raise ValueError("overlapping_research_areas")
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    values = list(points.values())
    for offset in range(0, len(values), 500):
        rows = (
            await admin.execute(
                text("""WITH points AS (
            SELECT id,ST_SetSRID(ST_Point(x,y),4326) point
            FROM jsonb_to_recordset(CAST(:points AS jsonb)) AS p(id text,x float8,y float8))
            SELECT p.id venue_id,a.id::text area_id,a.name FROM points p
            JOIN admin.research_area a ON a.area_type='municipality'
                AND a.geometry && p.point AND ST_Covers(a.geometry,p.point)
            ORDER BY p.id,a.id"""),
                {"points": json.dumps(values[offset : offset + 500])},
            )
        ).mappings()
        for r in rows:
            result[r["venue_id"]].append({"id": r["area_id"], "name": r["name"]})
    return True, dict(result)


@overload
async def extract_events(
    connection: AsyncConnection,
    admin: AsyncConnection | None,
    settings: Settings,
    now: datetime,
    limit: int | None = None,
    *,
    semantic: Literal[False] = False,
) -> tuple[list[EventDocument], int]: ...


@overload
async def extract_events(
    connection: AsyncConnection,
    admin: AsyncConnection | None,
    settings: Settings,
    now: datetime,
    limit: int | None = None,
    *,
    semantic: Literal[True],
) -> tuple[list[SemanticDocument], int]: ...


async def extract_events(
    connection: AsyncConnection,
    admin: AsyncConnection | None,
    settings: Settings,
    now: datetime,
    limit: int | None = None,
    *,
    semantic: bool = False,
) -> tuple[list[EventDocument], int] | tuple[list[SemanticDocument], int]:
    if limit is not None and not 1 <= limit <= 10000:
        raise ValueError("invalid_event_limit")
    if not settings.uranus_timestamp_timezone:
        raise ValueError("source_timezone_required")
    total = int(
        (
            await connection.execute(
                text(f"SELECT count(*) FROM uranus.event e WHERE {PUBLIC_EVENT}")
            )
        ).scalar_one()
    )
    if total > 10000 and limit is None:
        raise ValueError("event_snapshot_limit")
    rows = [
        dict(r)
        for r in (
            await connection.execute(
                text(EVENT_SQL),
                {
                    "limit": limit or 10000,
                    "source_tz": settings.uranus_timestamp_timezone,
                },
            )
        ).mappings()
    ]
    ids = [r["entity_id"] for r in rows]
    dates = [dict(r) for r in (await connection.execute(text(DATES_SQL), {"ids": ids})).mappings()]
    types = [dict(r) for r in (await connection.execute(text(TYPES_SQL), {"ids": ids})).mappings()]
    if len(dates) > 100000 or len(types) > 100000:
        raise ValueError("event_context_limit")
    available, memberships = await area_memberships(admin, dates)
    by_date: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    by_type: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for date in dates:
        by_date[date["event_uuid"]].append(date)
    for kind in types:
        by_type[kind["event_uuid"]].append(kind)
    documents: list[EventDocument] = []
    semantic_documents: list[SemanticDocument] = []
    local = now.astimezone(ZoneInfo(settings.event_timezone))
    for row in rows:
        event_dates = by_date[row["entity_id"]]
        assigned = [a for d in event_dates for a in memberships.get(str(d["venue_id"]), [])]
        context: dict[str, Any] = {"area_assignment_available": available}
        for key in ("venue_id", "venue_name", "space_id", "space_name"):
            context[key + "s"] = sorted({str(d[key]) for d in event_dates if d[key]})
        context["area_ids"] = sorted({a["id"] for a in assigned})
        context["area_names"] = sorted({a["name"] for a in assigned})
        context["accessibility"] = sorted(
            {
                d[key]
                for d in event_dates
                for key in ("venue_accessibility", "space_accessibility", "date_accessibility")
                if d[key]
            }
        )
        days = [d["start_date"].isoformat() for d in event_dates]
        context.update(
            first_date=days[0] if days else None,
            last_date=days[-1] if days else None,
            next_date=next(
                (d["start_date"].isoformat() for d in event_dates if is_upcoming_start(d, local)),
                None,
            ),
        )
        row["type_names"] = [t["type_name"] for t in by_type[row["entity_id"]]]
        genres = [t for t in by_type[row["entity_id"]] if t["genre_id"] != 0]
        row["genre_keys"] = sorted({f"{t['type_id']}:{t['genre_id']}" for t in genres})
        row["genre_names"] = sorted({t["genre_name"] for t in genres if t["genre_name"]})
        locations: dict[str, dict[str, Any]] = {}
        for date in event_dates:
            point = location(date["latitude"], date["longitude"])
            value = EffectiveLocation(
                effective_venue_id=date["venue_id"],
                effective_venue_name=public_clean(date["venue_name"]) or None,
                effective_space_id=date["space_id"],
                effective_space_name=public_clean(date["space_name"]) or None,
                effective_latitude=point["latitude"] if point else None,
                effective_longitude=point["longitude"] if point else None,
            ).model_dump(mode="json")
            locations[json.dumps(value, sort_keys=True)] = value
        context["effective_locations"] = [locations[k] for k in sorted(locations)]
        if semantic:
            semantic_documents.append(event_document(row, context))
        else:
            documents.append(document(row, context))
    corpus: list[EventDocument | SemanticDocument] = [*documents, *semantic_documents]
    if sum(len(s.text.encode()) for d in corpus for s in d.sections) > 64 * 1024 * 1024:
        raise ValueError("event_corpus_limit")
    if sum(len(d.model_dump_json().encode()) for d in semantic_documents) > 64 * 1024 * 1024:
        raise ValueError("semantic_corpus_limit")
    return (semantic_documents, total) if semantic else (documents, total)
