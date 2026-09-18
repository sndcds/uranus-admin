from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.errors import APIError
from app.repositories.activity_previews import activity_previews
from app.repositories.spatial import SPATIAL_TYPES, mixed_spatial_predicate
from app.schemas.action import Action
from app.schemas.activity import Activity, ActivityFilters, ActivityPage
from app.schemas.cursor import ActivityCursor, CursorPagination, decode, encode, scope
from app.schemas.finding import Pagination
from app.services.periods import period_window

# All source identifiers are constants. No projection, password, invitation or import tokens.
ENTITY_ACTIVITY_SQL = {
    "organization": """
SELECT 'organization'::text entity_type, o.uuid::text entity_key, o.name entity_name,
       o.uuid organization_id, o.name organization_name, o.created_at, NULL::text status
FROM uranus.organization o
""",
    "venue": """
SELECT 'venue', v.uuid::text, v.name, o.uuid, o.name, v.created_at, NULL
FROM uranus.venue v LEFT JOIN uranus.organization o ON o.uuid=v.org_uuid
""",
    "space": """
SELECT 'space', s.uuid::text, s.name, o.uuid, o.name, s.created_at, NULL
FROM uranus.space s LEFT JOIN uranus.venue v ON v.uuid=s.venue_uuid
LEFT JOIN uranus.organization o ON o.uuid=v.org_uuid
""",
    "event": """
SELECT 'event', e.uuid::text, e.title, o.uuid, o.name, e.created_at, e.release_status::text
FROM uranus.event e LEFT JOIN uranus.organization o ON o.uuid=e.org_uuid
""",
    "event_date": """
SELECT 'event_date', d.uuid::text, COALESCE(e.title,d.uuid::text), o.uuid, o.name,
       d.created_at, COALESCE(NULLIF(d.release_status::text,'inherited'),e.release_status::text)
FROM uranus.event_date d LEFT JOIN uranus.event e ON e.uuid=d.event_uuid
LEFT JOIN uranus.organization o ON o.uuid=e.org_uuid
""",
    "user": """
SELECT 'user', u.uuid::text, COALESCE(u.display_name,u.username,u.uuid::text), NULL, NULL,
       u.created_at, CASE WHEN u.is_active THEN 'active' ELSE 'inactive' END
FROM uranus."user" u
""",
}
ACTIVITY_SQL = (
    "\nUNION ALL\n".join(ENTITY_ACTIVITY_SQL.values())
    + """
UNION ALL
SELECT 'partner_request', 'partner-request:'||p.from_org_uuid||':'||p.to_org_uuid,
       COALESCE(f.name,p.from_org_uuid::text)||' → '||COALESCE(t.name,p.to_org_uuid::text),
       p.from_org_uuid, f.name, p.created_at, p.status
FROM uranus.organization_partner_request p
LEFT JOIN uranus.organization f ON f.uuid=p.from_org_uuid
LEFT JOIN uranus.organization t ON t.uuid=p.to_org_uuid
UNION ALL
SELECT 'team_membership', 'membership:'||m.org_uuid||':'||m.user_uuid,
       COALESCE(u.display_name,u.username,m.user_uuid::text), m.org_uuid, o.name, m.created_at,
       CASE WHEN m.has_joined THEN 'joined' ELSE 'invited' END
FROM uranus.organization_member_link m LEFT JOIN uranus.organization o ON o.uuid=m.org_uuid
LEFT JOIN uranus."user" u ON u.uuid=m.user_uuid
UNION ALL
SELECT 'image', i.uuid::text, COALESCE(i.alt_text,i.uuid::text), NULL,NULL,i.created_at,NULL
FROM uranus.pluto_image i
"""
)


# Reuse the existing safe name/context projections. Invitation statistics deliberately
# use invited_at, while default Activity and dashboard keep membership row creation.
STATISTICS_ACTIVITY_SQL = ACTIVITY_SQL.replace("m.created_at", "m.invited_at")


def creation_activity_sql(statistics: bool = False) -> str:
    if statistics:
        return (
            f"SELECT * FROM ({STATISTICS_ACTIVITY_SQL}) creations "
            "WHERE entity_type NOT IN ('event_date','image')"
        )
    return ACTIVITY_SQL


async def activity_page(
    connection: AsyncConnection,
    settings: Settings,
    filters: ActivityFilters,
    now: datetime,
    geo_scope_wkb: bytes | None = None,
) -> ActivityPage:
    if settings.uranus_timestamp_timezone is None:
        raise APIError(503, "source_timezone_unconfigured", "Source timezone must be configured.")
    if filters.geo_scope_id and filters.entity_type and filters.entity_type not in SPATIAL_TYPES:
        raise APIError(422, "invalid_input", "This activity type has no spatial membership.")
    cursor_mode = filters.cursor is not None
    expected_scope = scope(filters, timezone=settings.uranus_timestamp_timezone)
    position = (
        decode(filters.cursor, ActivityCursor, expected_scope)
        if filters.cursor is not None and filters.cursor != "start"
        else None
    )
    if position and ((position.created_at is None) != (filters.timestamp_state == "unknown")):
        raise APIError(422, "invalid_input", "Cursor timestamp state does not match.")
    start, end = filters.from_at, filters.to_at
    if filters.timestamp_state == "known" and not (start or end or filters.entity_key):
        window = period_window(filters.period or "24h", now, settings.admin_timezone)
        start, end = window.start, window.end
    if position:
        start, end = position.from_at, position.to_at
    params: dict[str, Any] = {
        "entity_type": filters.entity_type,
        "entity_key": filters.entity_key,
        "org": filters.organization_id,
        "start": start,
        "end": end,
        "tz": settings.uranus_timestamp_timezone,
        "limit": filters.page_size + int(cursor_mode),
        "offset": 0 if cursor_mode else (filters.page - 1) * filters.page_size,
    }
    where = """
    WHERE (CAST(:entity_type AS text) IS NULL OR entity_type=:entity_type)
      AND (CAST(:entity_key AS text) IS NULL OR entity_key=:entity_key)
      AND (CAST(:org AS uuid) IS NULL OR organization_id=:org
        OR (entity_type='user' AND EXISTS (
          SELECT 1 FROM uranus.organization_member_link m
          WHERE m.user_uuid::text=a.entity_key AND m.org_uuid=:org))
        OR (entity_type='partner_request' AND EXISTS (
          SELECT 1 FROM uranus.organization_partner_request p
          WHERE 'partner-request:'||p.from_org_uuid||':'||p.to_org_uuid=a.entity_key
            AND p.to_org_uuid=:org))
        OR (entity_type='image' AND EXISTS (
          SELECT 1 FROM uranus.pluto_image_link l
          LEFT JOIN uranus.venue v ON l.context='venue' AND v.uuid=l.context_uuid
          LEFT JOIN uranus.event e ON l.context='event' AND e.uuid=l.context_uuid
          WHERE l.pluto_image_uuid::text=a.entity_key AND
            ((l.context='organization' AND l.context_uuid=:org)
             OR v.org_uuid=:org OR e.org_uuid=:org))))
    """
    if geo_scope_wkb is not None:
        where += " AND " + mixed_spatial_predicate()
        params["geo_scope_wkb"] = geo_scope_wkb
    source_sql = creation_activity_sql(filters.creation_basis == "statistics")
    base = f"WITH a AS ({source_sql}) SELECT * FROM a {where}"
    unknown = int(
        (
            await connection.execute(
                text(f"SELECT COUNT(*) FROM ({base} AND created_at IS NULL) q"), params
            )
        ).scalar_one()
    )
    if filters.timestamp_state == "unknown":
        base += " AND created_at IS NULL"
        order = "entity_type, entity_key"  # Identity order only, never fabricated chronology.
    else:
        base += """ AND created_at IS NOT NULL
        AND (CAST(:start AS timestamptz) IS NULL OR created_at AT TIME ZONE :tz >= :start)
        AND (CAST(:end AS timestamptz) IS NULL OR created_at AT TIME ZONE :tz < :end)"""
        order = "created_at DESC, entity_type, entity_key"
    total = int(
        (await connection.execute(text(f"SELECT COUNT(*) FROM ({base}) q"), params)).scalar_one()
    )
    cursor_where = ""
    if position:
        params.update(
            cursor_type=position.entity_type,
            cursor_key=position.entity_key,
            cursor_time=position.created_at,
        )
        identity_after = "(entity_type,entity_key) > (:cursor_type,:cursor_key)"
        cursor_where = (
            f"WHERE {identity_after}"
            if position.created_at is None
            else (
                "WHERE (created_at < :cursor_time OR "
                f"(created_at = :cursor_time AND {identity_after}))"
            )
        )
    rows = (
        (
            await connection.execute(
                text(
                    "SELECT * FROM (SELECT entity_type, entity_key, entity_name, "
                    "organization_id, organization_name, "
                    f"status, created_at AT TIME ZONE :tz AS created_at FROM ({base}) q) projected "
                    f"{cursor_where} "
                    f"ORDER BY {order} LIMIT :limit OFFSET :offset"
                ),
                params,
            )
        )
        .mappings()
        .all()
    )
    has_more = cursor_mode and len(rows) > filters.page_size
    rows = rows[: filters.page_size]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = encode(
            ActivityCursor(
                scope=expected_scope,
                entity_type=last["entity_type"],
                entity_key=last["entity_key"],
                created_at=last["created_at"],
                from_at=start,
                to_at=end,
            )
        )
    source_items = [dict(row) for row in rows]
    previews = await activity_previews(connection, settings, source_items, now)
    items = []
    for data in source_items:
        data.update(previews.get((data["entity_type"], data["entity_key"]), {}))
        data["action"] = (
            Action(route="activity", entity_key=data["entity_key"], entity_type=data["entity_type"])
            if data["created_at"] is not None or data["entity_type"] == "image"
            else None
        )
        items.append(Activity.model_validate(data))
    return ActivityPage(
        items=items,
        cursor_pagination=CursorPagination(
            page_size=filters.page_size, next_cursor=next_cursor, has_more=has_more
        )
        if cursor_mode
        else None,
        observed_at=now,
        from_at=start,
        to_at=end,
        timestamp_state=filters.timestamp_state,
        unknown_timestamp_count=unknown,
        pagination=Pagination(
            page=filters.page,
            page_size=filters.page_size,
            total=total,
            pages=(total + filters.page_size - 1) // filters.page_size,
        ),
    )
