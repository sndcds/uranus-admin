"""Explicit safe projections; bounded SQL pages and batch previews, never domain writes."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.admin_tables import finding, record_mark
from app.config import Settings
from app.errors import APIError
from app.repositories.activity import ACTIVITY_SQL, ENTITY_ACTIVITY_SQL
from app.repositories.activity_previews import activity_previews
from app.repositories.graph import RELATIONS
from app.schemas.action import Action
from app.schemas.activity import Activity
from app.schemas.entities import (
    EntityDetail,
    EntityFacts,
    EntityFilters,
    EntityPage,
    EntityRecord,
    EntityRelations,
    EntitySection,
)
from app.schemas.finding import Pagination

SECTIONS = {
    "events": "event",
    "venues": "venue",
    "spaces": "space",
    "organizations": "organization",
    "users": "user",
    "images": "image",
}
SOURCES = {
    **ENTITY_ACTIVITY_SQL,
    "image": """
SELECT 'image'::text entity_type,i.uuid::text entity_key,
COALESCE(i.alt_text,i.uuid::text) entity_name,
NULL::uuid organization_id,NULL::text organization_name,i.created_at,NULL::text status
FROM uranus.pluto_image i
""",
}
SOURCES = {
    kind: f"({ENTITY_ACTIVITY_SQL['organization']} WHERE FALSE) UNION ALL {sql}"
    for kind, sql in SOURCES.items()
}
FACTS = {
    "event": """SELECT e.uuid id,e.description,v.name venue_name,s.name space_name,
        (SELECT count(*) FROM uranus.event_date d WHERE d.event_uuid=e.uuid) event_dates
        FROM uranus.event e LEFT JOIN uranus.venue v ON v.uuid=e.venue_uuid
        LEFT JOIN uranus.space s ON s.uuid=e.space_uuid WHERE e.uuid=ANY(:ids)""",
    "venue": """SELECT v.uuid id,
        (SELECT count(*) FROM uranus.space s WHERE s.venue_uuid=v.uuid) spaces
        FROM uranus.venue v WHERE v.uuid=ANY(:ids)""",
    "space": """SELECT s.uuid id,v.name venue_name FROM uranus.space s
        LEFT JOIN uranus.venue v ON v.uuid=s.venue_uuid WHERE s.uuid=ANY(:ids)""",
    "organization": """SELECT o.uuid id,
        (SELECT count(*) FROM uranus.venue v WHERE v.org_uuid=o.uuid) venues,
        (SELECT count(*) FROM uranus.event e WHERE e.org_uuid=o.uuid) events,
        (SELECT count(*) FROM uranus.organization_member_link m WHERE m.org_uuid=o.uuid) memberships
        FROM uranus.organization o WHERE o.uuid=ANY(:ids)""",
    "user": """SELECT u.uuid id,u.username,
        (SELECT count(*) FROM uranus.organization_member_link m WHERE m.user_uuid=u.uuid)
        memberships
        FROM uranus."user" u WHERE u.uuid=ANY(:ids)""",
    "image": """SELECT i.uuid id,
        (SELECT count(*) FROM uranus.pluto_image_link l WHERE l.pluto_image_uuid=i.uuid)
        image_links,
        NOT EXISTS(SELECT 1 FROM uranus.pluto_image_link l WHERE l.pluto_image_uuid=i.uuid) orphan
        FROM uranus.pluto_image i WHERE i.uuid=ANY(:ids)""",
}


def pagination(page: int, size: int, total: int) -> Pagination:
    return Pagination(page=page, page_size=size, total=total, pages=(total + size - 1) // size)


async def enrich(
    connection: AsyncConnection, settings: Settings, rows: list[dict[str, Any]], now: datetime
) -> list[Activity]:
    previews = await activity_previews(connection, settings, rows, now)
    return [
        Activity.model_validate(
            {
                **row,
                **previews.get((row["entity_type"], row["entity_key"]), {}),
                "action": Action(
                    route="activity", entity_type=row["entity_type"], entity_key=row["entity_key"]
                ),
            }
        )
        for row in rows
    ]


async def records(
    connection: AsyncConnection,
    settings: Settings,
    kind: str,
    rows: list[dict[str, Any]],
    now: datetime,
) -> list[EntityRecord]:
    if not rows:
        return []
    facts = (
        await connection.execute(
            text(FACTS[kind]), {"ids": [UUID(row["entity_key"]) for row in rows]}
        )
    ).mappings()
    by_id = {str(row["id"]): EntityFacts.model_validate(row) for row in facts}
    return [
        EntityRecord(**item.model_dump(), facts=by_id[item.entity_key])
        for item in await enrich(connection, settings, rows, now)
    ]


def require_timezone(settings: Settings) -> str:
    if settings.uranus_timestamp_timezone is None:
        raise APIError(503, "source_timezone_unconfigured", "Source timezone must be configured.")
    return settings.uranus_timestamp_timezone


async def entity_page(
    connection: AsyncConnection,
    settings: Settings,
    section: EntitySection,
    filters: EntityFilters,
    now: datetime,
) -> EntityPage:
    kind = SECTIONS[section]
    q = filters.q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    params = {
        "q": f"%{q}%",
        "org": filters.organization_id,
        "status": filters.status,
        "size": filters.page_size,
        "offset": (filters.page - 1) * filters.page_size,
        "tz": require_timezone(settings),
    }
    base = f"""SELECT * FROM ({SOURCES[kind]}) a
        WHERE (entity_name ILIKE :q OR entity_key ILIKE :q)
        AND (CAST(:status AS text) IS NULL OR status=:status)
        AND (CAST(:org AS uuid) IS NULL OR organization_id=:org
          OR (entity_type='user' AND EXISTS (SELECT 1 FROM uranus.organization_member_link m
              WHERE m.user_uuid::text=a.entity_key AND m.org_uuid=:org))
          OR (entity_type='image' AND EXISTS (SELECT 1 FROM uranus.pluto_image_link l
              LEFT JOIN uranus.venue v ON l.context='venue' AND v.uuid=l.context_uuid
              LEFT JOIN uranus.event e ON l.context='event' AND e.uuid=l.context_uuid
              WHERE l.pluto_image_uuid::text=a.entity_key AND
                ((l.context='organization' AND l.context_uuid=:org) OR v.org_uuid=:org
                 OR e.org_uuid=:org))))"""
    total = int(
        (await connection.execute(text(f"SELECT count(*) FROM ({base}) a"), params)).scalar_one()
    )
    rows = (
        await connection.execute(
            text(f"""SELECT entity_type,entity_key,entity_name,
        organization_id,organization_name,status,created_at AT TIME ZONE :tz created_at
        FROM ({base}) a ORDER BY lower(entity_name) COLLATE "C",entity_key COLLATE "C"
        LIMIT :size OFFSET :offset"""),
            params,
        )
    ).mappings()
    return EntityPage(
        items=await records(connection, settings, kind, [dict(r) for r in rows], now),
        pagination=pagination(filters.page, filters.page_size, total),
        observed_at=now,
    )


def related_sql(kind: str) -> str:
    branches = []
    for _, src_type, src, dst_type, dst, table, condition in RELATIONS:
        for own_type, own, other_type, other in (
            (src_type, src, dst_type, dst),
            (dst_type, dst, src_type, src),
        ):
            if own_type == kind:
                branches.append(
                    f"SELECT '{other_type}' entity_type,({other})::text entity_key "
                    f"FROM {table} WHERE ({own})=:id AND ({other}) IS NOT NULL AND {condition}"
                )
    if kind in {"organization", "user"}:
        col = "org_uuid" if kind == "organization" else "user_uuid"
        branches.append(
            "SELECT 'team_membership','membership:'||m.org_uuid||':'||m.user_uuid "
            f"FROM uranus.organization_member_link m WHERE m.{col}=:id"
        )
    if kind == "organization":
        branches.append(
            "SELECT 'partner_request','partner-request:'||p.from_org_uuid||':'||p.to_org_uuid "
            "FROM uranus.organization_partner_request p "
            "WHERE p.from_org_uuid=:id OR p.to_org_uuid=:id"
        )
    if kind == "image":
        branches.append(
            "SELECT context,context_uuid::text FROM uranus.pluto_image_link "
            "WHERE pluto_image_uuid=:id AND context IN ('organization','venue','event')"
        )
    elif kind in {"organization", "venue", "event"}:
        branches.append(
            f"SELECT 'image',pluto_image_uuid::text FROM uranus.pluto_image_link "
            f"WHERE context='{kind}' AND context_uuid=:id"
        )
    return " UNION ".join(branches)


async def entity_detail(
    connection: AsyncConnection,
    settings: Settings,
    section: EntitySection,
    key: UUID,
    page: int,
    now: datetime,
) -> EntityDetail:
    kind = SECTIONS[section]
    params = {
        "key": str(key),
        "id": key,
        "tz": require_timezone(settings),
        "offset": (page - 1) * 25,
    }
    row = (
        (
            await connection.execute(
                text(f"""SELECT entity_type,entity_key,entity_name,
        organization_id,organization_name,status,created_at AT TIME ZONE :tz created_at
        FROM ({SOURCES[kind]}) a WHERE entity_key=:key"""),
                params,
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise APIError(404, "record_not_found", "Record not found.")
    base = f"""WITH links(entity_type,entity_key) AS ({related_sql(kind)}), a AS ({ACTIVITY_SQL})
        SELECT a.* FROM a JOIN links USING (entity_type,entity_key)"""
    total = int(
        (await connection.execute(text(f"SELECT count(*) FROM ({base}) r"), params)).scalar_one()
    )
    related = (
        await connection.execute(
            text(f"""SELECT entity_type,entity_key,entity_name,
        organization_id,organization_name,status,created_at AT TIME ZONE :tz created_at
        FROM ({base}) r ORDER BY entity_type COLLATE "C",lower(entity_name) COLLATE "C",entity_key
        LIMIT 25 OFFSET :offset"""),
            params,
        )
    ).mappings()
    return EntityDetail(
        item=(await records(connection, settings, kind, [dict(row)], now))[0],
        related=EntityRelations(
            items=await enrich(connection, settings, [dict(r) for r in related], now),
            pagination=pagination(page, 25, total),
        ),
        observed_at=now,
    )


async def workflow_counts(admin: AsyncConnection, items: list[EntityRecord]) -> None:
    if not items:
        return
    kind = items[0].entity_type
    keys = [item.entity_key for item in items]
    for table, field in ((finding, "finding_count"), (record_mark, "mark_count")):
        conditions = [table.c.entity_type == kind, table.c.entity_key.in_(keys)]
        if field == "finding_count":
            conditions.append(table.c.status != "resolved")
        rows = await admin.execute(
            select(table.c.entity_key, func.count()).where(*conditions).group_by(table.c.entity_key)
        )
        counts = dict(rows.tuples().all())
        for item in items:
            setattr(item, field, counts.get(item.entity_key, 0))
