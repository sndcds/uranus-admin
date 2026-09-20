from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.repositories.query import ReadQuery
from app.schemas.queues import QueueFilters, QueueKind

QUEUE_SQL = {
    "partner_requests": """
SELECT p.from_org_uuid, p.to_org_uuid, p.from_user_uuid AS user_id, p.status, p.created_at,
 f.name AS from_name, t.name AS to_name, COALESCE(u.display_name,u.username) AS user_name,
 u.uuid IS NOT NULL AS user_exists,
 EXISTS(SELECT 1 FROM uranus.organization_access_grants g
        WHERE g.src_org_uuid=p.to_org_uuid AND g.dst_org_uuid=p.from_org_uuid) AS grant_exists
FROM uranus.organization_partner_request p
LEFT JOIN uranus.organization f ON f.uuid=p.from_org_uuid
LEFT JOIN uranus.organization t ON t.uuid=p.to_org_uuid
LEFT JOIN uranus."user" u ON u.uuid=p.from_user_uuid
""",
    "team_invitations": """
SELECT m.org_uuid, o.name AS organization_name, m.user_uuid AS user_id,
 COALESCE(u.display_name,u.username) AS user_name, m.created_at, m.invited_at, m.has_joined
FROM uranus.organization_member_link m
LEFT JOIN uranus.organization o ON o.uuid=m.org_uuid
LEFT JOIN uranus."user" u ON u.uuid=m.user_uuid

""",
    "user_activation": """
SELECT u.uuid AS user_id, COALESCE(u.display_name,u.username) AS user_name,
 u.created_at, u.is_active,
 COALESCE(m.organizations, ARRAY[]::uuid[]) AS organizations
FROM uranus."user" u
LEFT JOIN (SELECT user_uuid, array_agg(org_uuid ORDER BY org_uuid) AS organizations
 FROM uranus.organization_member_link GROUP BY user_uuid) m ON m.user_uuid=u.uuid
""",
}


async def queue_rows(connection: AsyncConnection, kind: QueueKind) -> list[dict[str, Any]]:
    return [dict(row) for row in (await connection.execute(text(QUEUE_SQL[kind]))).mappings()]


# All SQL fragments are code-owned; request values are bound parameters.
QUEUE_EXPRESSIONS = {
    "partner_requests": (
        "'partner-request:' || from_org_uuid::text || ':' || to_org_uuid::text",
        "status",
        "created_at",
        "TRUE",
        "(from_org_uuid=:organization_id OR to_org_uuid=:organization_id)",
    ),
    "team_invitations": (
        "'membership:' || org_uuid::text || ':' || user_id::text",
        "CASE WHEN has_joined THEN 'joined' ELSE 'invited' END",
        "invited_at",
        "NOT COALESCE(has_joined, false)",
        "org_uuid=:organization_id",
    ),
    "user_activation": (
        "user_id::text",
        "CASE WHEN is_active THEN 'active' ELSE 'inactive' END",
        "created_at",
        "NOT COALESCE(is_active, false)",
        "EXISTS (SELECT 1 FROM uranus.organization_member_link m "
        "WHERE m.user_uuid=s.user_id AND m.org_uuid=:organization_id)",
    ),
}


def queue_page_queries(
    kind: QueueKind,
    filters: QueueFilters,
    now: datetime,
    source_timezone: str,
) -> dict[str, ReadQuery]:
    key, status, basis, active, organization = QUEUE_EXPRESSIONS[kind]
    conditions = [active]
    params: dict[str, Any] = {
        "now": now,
        "timezone": source_timezone,
        "limit": filters.page_size,
        "offset": (filters.page - 1) * filters.page_size,
    }
    for name, expression in (
        ("organization_id", organization),
        ("entity_key", f"({key})=:entity_key"),
        ("status", f"({status})=:status"),
    ):
        value = getattr(filters, name)
        if value is not None:
            conditions.append(expression)
            params[name] = value
    # Match Python timedelta.days, including unknown/future invitation timestamps.
    age = (
        f"CASE WHEN ({basis} AT TIME ZONE :timezone) <= :now THEN "
        f"floor(extract(epoch FROM (CAST(:now AS timestamptz) - "
        f"({basis} AT TIME ZONE :timezone))) / 86400)::integer END"
    )
    if filters.min_age_days is not None:
        conditions.append(f"({age}) >= :min_age_days")
        params["min_age_days"] = filters.min_age_days
    source = f"FROM ({QUEUE_SQL[kind]}) s WHERE {' AND '.join(conditions)}"
    return {
        "count": ReadQuery(text(f"SELECT count(*) {source}"), params),
        "records": ReadQuery(
            text(
                f'SELECT s.* {source} ORDER BY ({age}) DESC NULLS LAST, ({key}) COLLATE "C" '
                "LIMIT :limit OFFSET :offset"
            ),
            params,
        ),
    }


async def queue_page_rows(
    connection: AsyncConnection,
    kind: QueueKind,
    filters: QueueFilters,
    now: datetime,
    source_timezone: str,
) -> tuple[list[dict[str, Any]], int]:
    queries = queue_page_queries(kind, filters, now, source_timezone)
    total = int(
        (
            await connection.execute(queries["count"].statement, queries["count"].parameters)
        ).scalar_one()
    )
    rows = (
        await connection.execute(queries["records"].statement, queries["records"].parameters)
    ).mappings()
    return [dict(row) for row in rows], total
