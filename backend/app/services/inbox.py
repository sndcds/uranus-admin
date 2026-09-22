from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.repositories.activity import ACTIVITY_SQL
from app.repositories.notifications import local_day
from app.schemas.action import Action
from app.schemas.assignments import (
    InboxCounts,
    InboxFilters,
    InboxItem,
    InboxPage,
)
from app.schemas.finding import Pagination
from app.services.assignments import map_assignment

BASE_SQL = """
WITH geocode_counts AS (
 SELECT c.request_id,count(*)::integer AS candidate_count
 FROM admin.geocode_candidate c
 JOIN admin.geocode_request r ON r.id=c.request_id AND r.generation=c.generation
 GROUP BY c.request_id
), tasks AS (
 SELECT 'assignment:' || a.id::text AS id, 'assignment' AS kind,
        CASE WHEN a.finding_id IS NOT NULL THEN 'Qualitätsprüfung'
        WHEN a.workflow_type='geocode_request' THEN 'Standortvorschlag'
        ELSE 'Benachrichtigung' END AS title,
        CASE WHEN a.finding_id IS NOT NULL THEN left(f.message,5000)
        WHEN a.workflow_type='geocode_request' THEN
          CASE WHEN g.status='candidate' THEN 'Standortvorschlag vorhanden'
               WHEN g.status='ambiguous' THEN 'Mehrere mögliche Standorte'
               WHEN g.status='not_found' THEN 'Kein Geocoding-Ergebnis'
               WHEN g.status='insufficient_input' THEN 'Zu wenig Adressdaten'
               ELSE 'Geocoding fehlgeschlagen' END
        ELSE 'Fehlgeschlagene Zustellung prüfen' END AS summary,
        left(COALESCE(f.metadata->'finding'->>'entity_name',a.entity_key),500)
          AS fallback_entity_name,
        a.entity_type,a.entity_key,
        CASE WHEN a.finding_id IS NOT NULL THEN f.severity ELSE NULL END AS severity,
        a.status,a.updated_at AS occurred_at,a.due_at,
        a.id AS assignment_id,a.finding_id,a.workflow_type,a.workflow_key,
        a.assigned_to_admin_id,a.assigned_by_subject,
        a.created_at AS assignment_created_at,a.updated_at AS assignment_updated_at,
        a.completed_at,a.version,aa.login AS assigned_to_login,
        CASE WHEN a.finding_id IS NOT NULL THEN f.rule ELSE NULL END AS rule,
        CASE WHEN a.workflow_type='geocode_request' THEN g.status
             WHEN a.workflow_type='notification_delivery' THEN d.status END AS workflow_status,
        CASE WHEN a.workflow_type='geocode_request' THEN COALESCE(gc.candidate_count,0) END
          AS candidate_count
 FROM admin.assignment a
 JOIN admin.auth_account aa ON aa.id=a.assigned_to_admin_id
 LEFT JOIN admin.finding f ON f.id=a.finding_id
 LEFT JOIN admin.geocode_request g ON a.workflow_type='geocode_request'
   AND a.workflow_key=g.id::text
 LEFT JOIN geocode_counts gc ON gc.request_id=g.id
 LEFT JOIN admin.notification_delivery d ON a.workflow_type='notification_delivery'
   AND a.workflow_key=d.id::text
 WHERE a.status IN ('open','in_progress')

 UNION ALL

 SELECT 'finding:' || f.id,'finding','Qualitätsprüfung',left(f.message,5000),
        left(COALESCE(f.metadata->'finding'->>'entity_name',f.entity_id),500),
        f.entity_type,f.entity_id,f.severity,f.status,f.last_seen_at,NULL,
        NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,f.rule,NULL,NULL
 FROM admin.finding f
 WHERE f.status IN ('open','in_progress')
   AND NOT EXISTS (SELECT 1 FROM admin.assignment a
                   WHERE a.finding_id=f.id AND a.status IN ('open','in_progress'))

 UNION ALL

 SELECT 'geocode_request:' || g.id::text,'geocode_request','Standortvorschlag',
        CASE WHEN g.status='candidate' THEN 'Standortvorschlag vorhanden'
             WHEN g.status='ambiguous' THEN 'Mehrere mögliche Standorte'
             WHEN g.status='not_found' THEN 'Kein Geocoding-Ergebnis'
             WHEN g.status='insufficient_input' THEN 'Zu wenig Adressdaten'
             ELSE 'Geocoding fehlgeschlagen' END,
        g.entity_key::text,
        g.entity_type,g.entity_key::text,
        CASE WHEN g.status='failed' THEN 'error' ELSE 'warning' END,g.status,g.updated_at,NULL,
        NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,g.status,
        COALESCE(gc.candidate_count,0)
 FROM admin.geocode_request g
 LEFT JOIN geocode_counts gc ON gc.request_id=g.id
 WHERE g.status IN ('candidate','ambiguous','not_found','failed')
   AND NOT EXISTS (SELECT 1 FROM admin.assignment a
                   WHERE a.workflow_type='geocode_request' AND a.workflow_key=g.id::text
                     AND a.status IN ('open','in_progress'))

 UNION ALL

 SELECT 'notification_delivery:' || d.id::text,'notification_delivery','Benachrichtigung',
        'Fehlgeschlagene Zustellung prüfen',d.organization_id::text,
        'organization',d.organization_id::text,
        CASE WHEN d.status='permanent_failure' THEN 'error' ELSE 'warning' END,
        d.status,d.updated_at,NULL,
        NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,d.status,NULL
 FROM admin.notification_delivery d
 WHERE d.status IN ('failed','permanent_failure')
   AND NOT EXISTS (SELECT 1 FROM admin.assignment a
                   WHERE a.workflow_type='notification_delivery' AND a.workflow_key=d.id::text
                     AND a.status IN ('open','in_progress'))
)
"""

PRESENTATION_TYPES = {"event", "organization", "venue", "space", "user", "team_membership", "image"}


def account_id(subject: str) -> UUID | None:
    if not subject.startswith("admin:"):
        return None
    try:
        return UUID(subject.removeprefix("admin:"))
    except ValueError:
        return None


def conditions(filters: InboxFilters) -> str:
    parts = ["TRUE"]
    if filters.scope == "mine":
        parts.append("assigned_to_admin_id=:current_admin_id")
    elif filters.scope == "unassigned":
        parts.append("assignment_id IS NULL")
    if filters.attention == "critical":
        parts.append("severity='error'")
    elif filters.attention == "due_today":
        parts.append("due_at >= :day_start AND due_at < :day_end")
    elif filters.attention == "overdue":
        parts.append("due_at < :now")
    if filters.kind:
        parts.append("kind=:kind")
    if filters.entity_type:
        parts.append("entity_type=:entity_type")
    return " AND ".join(parts)


def params(filters: InboxFilters, now: datetime, timezone: str, subject: str) -> dict[str, Any]:
    day_start, day_end = local_day(now, timezone)
    return {
        "current_admin_id": account_id(subject),
        "day_start": day_start,
        "day_end": day_end,
        "now": now,
        "kind": filters.kind,
        "entity_type": filters.entity_type,
        "limit": filters.page_size,
        "offset": (filters.page - 1) * filters.page_size,
    }


def item_href(row: dict[str, Any]) -> str:
    if row["kind"] == "finding" or (row["kind"] == "assignment" and row.get("finding_id")):
        return "/findings?" + urlencode(
            {"entity_key": row["entity_key"], "rule": row.get("rule") or ""}
        )
    if row.get("workflow_type") == "geocode_request" and row.get("workflow_key"):
        return f"/geocoding/{row['workflow_key']}"
    if row.get("workflow_type") == "notification_delivery" and row.get("workflow_key"):
        return f"/notifications/deliveries/{row['workflow_key']}"
    if row["kind"] == "geocode_request":
        return f"/geocoding/{row['id'].split(':', 1)[1]}"
    if row["kind"] == "notification_delivery":
        return f"/notifications/deliveries/{row['id'].split(':', 1)[1]}"
    return "/inbox"


async def source_presentations(
    source: AsyncConnection, rows: list[dict[str, Any]]
) -> dict[tuple[str, str], dict[str, Any]]:
    identities = sorted(
        {
            (row["entity_type"], row["entity_key"])
            for row in rows
            if row["entity_type"] in PRESENTATION_TYPES
        }
    )
    if not identities:
        return {}
    records = (
        await source.execute(
            text(
                "SELECT entity_type,entity_key,left(entity_name,500) AS entity_name,"
                "left(organization_name,500) AS organization_name "
                f"FROM ({ACTIVITY_SQL}) source_entities "
                "WHERE EXISTS (SELECT 1 FROM unnest(CAST(:types AS text[]),"
                "CAST(:keys AS text[])) requested(entity_type,entity_key) "
                "WHERE requested.entity_type=source_entities.entity_type "
                "AND requested.entity_key=source_entities.entity_key)"
            ),
            {
                "types": [identity[0] for identity in identities],
                "keys": [identity[1] for identity in identities],
            },
        )
    ).mappings()
    return {(row["entity_type"], row["entity_key"]): dict(row) for row in records}


def map_item(
    row: dict[str, Any],
    presentation: dict[str, Any] | None,
    now: datetime,
    day_start: datetime,
    day_end: datetime,
) -> InboxItem:
    assigned = None
    if row.get("assignment_id"):
        assigned = map_assignment(
            {
                "id": row["assignment_id"],
                "finding_id": row["finding_id"],
                "workflow_type": row["workflow_type"],
                "workflow_key": row["workflow_key"],
                "entity_type": row["entity_type"],
                "entity_key": row["entity_key"],
                "assigned_to_admin_id": row["assigned_to_admin_id"],
                "assigned_by_subject": row["assigned_by_subject"],
                "status": row["status"],
                "due_at": row["due_at"],
                "created_at": row["assignment_created_at"],
                "updated_at": row["assignment_updated_at"],
                "completed_at": row["completed_at"],
                "version": row["version"],
                "assigned_to_login": row["assigned_to_login"],
            }
        )
    due_at = row["due_at"]
    entity_name = (presentation or {}).get("entity_name") or row["fallback_entity_name"]
    entity_action = (
        Action(
            route="activity",
            entity_type=row["entity_type"],
            entity_key=row["entity_key"],
        )
        if presentation
        else None
    )
    return InboxItem.model_validate(
        {
            **row,
            "entity_name": entity_name,
            "organization_name": (presentation or {}).get("organization_name"),
            "entity_action": entity_action,
            "assignment": assigned,
            "is_overdue": due_at is not None and due_at < now,
            "due_today": due_at is not None and day_start <= due_at < day_end,
            "href": item_href(row),
        }
    )


async def inbox_page(
    admin: AsyncConnection,
    source: AsyncConnection,
    filters: InboxFilters,
    now: datetime,
    timezone: str,
    subject: str,
) -> InboxPage:
    values = params(filters, now, timezone, subject)
    where = conditions(filters)
    records_sql = text(
        BASE_SQL
        + f"""SELECT * FROM tasks WHERE {where}
        ORDER BY (due_at < :now) DESC NULLS LAST,
                 CASE severity WHEN 'error' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                 due_at ASC NULLS LAST, occurred_at DESC, id COLLATE "C"
        LIMIT :limit OFFSET :offset"""
    )
    count_sql = text(BASE_SQL + f"SELECT count(*) FROM tasks WHERE {where}")
    summary_sql = text(
        BASE_SQL
        + """SELECT
        count(*) FILTER (WHERE severity='error') AS critical,
        count(*) FILTER (WHERE assigned_to_admin_id=:current_admin_id) AS mine,
        count(*) FILTER (WHERE assignment_id IS NULL) AS unassigned,
        count(*) FILTER (WHERE due_at>=:day_start AND due_at<:day_end) AS due_today,
        count(*) FILTER (WHERE due_at<:now) AS overdue FROM tasks"""
    )
    day_start, day_end = local_day(now, timezone)
    async with admin.begin():
        await admin.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        total = int((await admin.execute(count_sql, values)).scalar_one())
        summary = dict((await admin.execute(summary_sql, values)).mappings().one())
        rows = [dict(row) for row in (await admin.execute(records_sql, values)).mappings()]
    presentations = await source_presentations(source, rows)
    return InboxPage(
        items=[
            map_item(
                row,
                presentations.get((row["entity_type"], row["entity_key"])),
                now,
                day_start,
                day_end,
            )
            for row in rows
        ],
        counts=InboxCounts.model_validate(summary),
        pagination=Pagination(
            page=filters.page,
            page_size=filters.page_size,
            total=total,
            pages=(total + filters.page_size - 1) // filters.page_size,
        ),
        observed_at=now,
    )
