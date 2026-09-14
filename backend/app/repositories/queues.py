from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.schemas.queues import QueueKind

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
 ARRAY(SELECT m.org_uuid FROM uranus.organization_member_link m
 WHERE m.user_uuid=u.uuid) AS organizations
FROM uranus."user" u
""",
}


async def queue_rows(connection: AsyncConnection, kind: QueueKind) -> list[dict[str, Any]]:
    return [dict(row) for row in (await connection.execute(text(QUEUE_SQL[kind]))).mappings()]
