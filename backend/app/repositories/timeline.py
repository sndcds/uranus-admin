"""Server-side entity timeline aggregation with fixed projections and keyset pagination."""

from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.errors import APIError
from app.repositories.created_period import require_timezone
from app.schemas.cursor import CursorPagination, TimelineCursor, decode, encode, scope
from app.schemas.timeline import (
    TimelineEntityType,
    TimelineFilters,
    TimelineItem,
    TimelineMetadata,
    TimelinePage,
)

SOURCE_TABLES: dict[TimelineEntityType, tuple[str, str]] = {
    "event": ("uranus.event", "e"),
    "organization": ("uranus.organization", "o"),
    "venue": ("uranus.venue", "v"),
    "space": ("uranus.space", "s"),
    "user": ('uranus."user"', "u"),
    "image": ("uranus.pluto_image", "i"),
}

ENTITY_TYPE_LABELS: dict[TimelineEntityType, str] = {
    "event": "event",
    "organization": "organization",
    "venue": "venue",
    "space": "space",
    "user": "user",
    "image": "image",
}

ADMIN_EVENTS = """
SELECT 'finding:' || fe.id::text id, 'finding_' || fe.kind kind, fe.occurred_at,
       left(fe.actor,256) actor, fe.status, fe.finding_id resource_id, fe.rule, fe.severity,
       fe.field, left(CASE WHEN fe.comment IS NULL THEN fe.message
                      ELSE fe.message || E'\n' || fe.comment END,5000) summary,
       NULL::integer generation, NULL::double precision score, NULL::integer http_status
FROM admin.finding_event fe
WHERE fe.entity_type=:entity_type AND fe.entity_key=:entity_key
UNION ALL
SELECT 'mark:' || me.id::text, 'mark_' || me.kind, me.created_at,
       left(me.author,256) actor, me.status, me.mark_id::text, NULL, NULL, NULL,
       COALESCE(me.note, me.reason_detail), NULL, NULL, NULL
FROM admin.record_mark_event me
JOIN admin.record_mark m ON m.id=me.mark_id
WHERE m.entity_type=:entity_type AND m.entity_key=:entity_key
UNION ALL
SELECT 'assignment:' || ae.id::text,
       CASE WHEN ae.kind='updated' AND ae.snoozed_until IS DISTINCT FROM ae.previous_snooze
            THEN CASE WHEN ae.snoozed_until IS NULL THEN 'assignment_unsnoozed'
                      ELSE 'assignment_snoozed' END
            ELSE 'assignment_' || ae.kind END, ae.occurred_at,
       left(ae.actor,256), ae.status, ae.assignment_id::text, NULL, NULL, NULL,
       'Zuständig: ' || aa.login || ' · ' ||
       CASE WHEN ae.snoozed_until IS NULL THEN 'Keine organisatorische Wiedervorlage'
            ELSE 'Wiedervorlage: ' ||
                 to_char(ae.snoozed_until AT TIME ZONE :admin_tz,'DD.MM.YYYY, HH24:MI') ||
                 ' (' || :admin_tz || ')' END, NULL, NULL, NULL
FROM (
 SELECT ae.*, lag(ae.snoozed_until) OVER (PARTITION BY ae.assignment_id ORDER BY ae.version)
     AS previous_snooze
 FROM admin.assignment_event ae
 JOIN admin.assignment context ON context.id=ae.assignment_id
 WHERE context.entity_type=:entity_type AND context.entity_key=:entity_key
) ae
JOIN admin.assignment a ON a.id=ae.assignment_id
JOIN admin.auth_account aa ON aa.id=ae.assigned_to_admin_id
WHERE a.entity_type=:entity_type AND a.entity_key=:entity_key
UNION ALL
SELECT 'delivery:' || d.id::text, 'notification_delivery',
       COALESCE(d.sent_at,d.sending_at,d.queued_at,d.created_at),
       NULL, d.status, d.id::text, NULL, NULL, NULL,
       left(d.subject,5000) summary, NULL, NULL, NULL
FROM admin.notification_delivery d
WHERE EXISTS (
    SELECT 1 FROM admin.notification_delivery_item di
    JOIN admin.notification n ON n.id=di.notification_id
    WHERE di.delivery_id=d.id AND (
        (n.entity_type=:entity_type AND n.entity_key=:entity_key)
        OR (:entity_type='organization' AND n.organization_id=:entity_uuid)
    )
)
UNION ALL
SELECT 'url-check:' || uc.id, 'url_check', uc.last_checked_at,
       NULL, uc.status, uc.id, NULL, NULL, uc.field,
       CASE WHEN uc.status_code IS NULL THEN uc.field || ': ' || uc.status
            ELSE uc.field || ': HTTP ' || uc.status_code::text END,
       NULL, NULL, uc.status_code
FROM admin.url_check uc
WHERE uc.source_type=:entity_type AND uc.source_key=:entity_key
  AND uc.last_checked_at IS NOT NULL
UNION ALL
SELECT 'geocode-request:' || gr.id::text, 'geocode_request', gr.created_at,
       NULL, gr.status, gr.id::text, NULL, NULL, NULL,
       'Standortprüfung vorgemerkt', gr.generation, NULL, NULL
FROM admin.geocode_request gr
WHERE gr.entity_type=:entity_type AND gr.entity_key=:entity_uuid
UNION ALL
SELECT 'geocode-result:' || gc.id::text, 'geocode_result', gc.created_at,
       NULL, gr.status, gr.id::text, NULL, NULL, NULL,
       gc.display_name, gc.generation, gc.match_score, NULL
FROM admin.geocode_candidate gc
JOIN admin.geocode_request gr ON gr.id=gc.request_id
WHERE gr.entity_type=:entity_type AND gr.entity_key=:entity_uuid AND gc.rank=1
UNION ALL
SELECT 'geocode-result:' || gr.id::text || ':' || gr.generation::text,
       'geocode_result', gr.checked_at, NULL, gr.status, gr.id::text,
       NULL, NULL, NULL, NULL, gr.generation, NULL, NULL
FROM admin.geocode_request gr
WHERE gr.entity_type=:entity_type AND gr.entity_key=:entity_uuid
  AND gr.checked_at IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM admin.geocode_candidate gc
      WHERE gc.request_id=gr.id AND gc.generation=gr.generation AND gc.rank=1
  )
"""


def source_events_sql(entity_type: TimelineEntityType, cursor: TimelineCursor | None) -> str:
    table, alias = SOURCE_TABLES[entity_type]
    entity_label = ENTITY_TYPE_LABELS[entity_type]
    branches = [
        f"""SELECT 'source-created:{entity_label}:' || {alias}.uuid::text id,
        'source_created'::text kind, {alias}.created_at AT TIME ZONE :tz occurred_at,
        NULL::text actor, NULL::text status, {alias}.uuid::text resource_id,
        NULL::text rule, NULL::text severity, NULL::text field,
        'In der Uranus-Quelle angelegt'::text summary,
        NULL::integer generation, NULL::double precision score, NULL::integer http_status
        FROM {table} {alias} WHERE {alias}.uuid=:entity_uuid AND {alias}.created_at IS NOT NULL""",
        f"""SELECT 'source-updated:{entity_label}:' || {alias}.uuid::text,
        'source_updated', {alias}.modified_at AT TIME ZONE :tz,
        NULL, NULL, {alias}.uuid::text, NULL, NULL, NULL,
        'Die Quelle weist einen Änderungszeitpunkt aus; geänderte Felder sind nicht belegt.',
        NULL, NULL, NULL
        FROM {table} {alias} WHERE {alias}.uuid=:entity_uuid
        AND {alias}.modified_at IS NOT NULL
        AND ({alias}.created_at IS NULL OR {alias}.modified_at>{alias}.created_at)""",
    ]
    if entity_type in {"organization", "user"}:
        own = "m.org_uuid" if entity_type == "organization" else "m.user_uuid"
        branches.append(
            f"""SELECT 'team-invitation:' || m.org_uuid::text || ':' || m.user_uuid::text || ':' ||
            extract(epoch FROM m.invited_at)::text, 'team_invitation',
            m.invited_at AT TIME ZONE :tz, NULL,
            CASE WHEN m.has_joined THEN 'joined' ELSE 'invited' END,
            'membership:' || m.org_uuid::text || ':' || m.user_uuid::text,
            NULL, NULL, NULL, 'Teameinladung erfasst', NULL, NULL, NULL
            FROM uranus.organization_member_link m
            WHERE {own}=:entity_uuid AND m.invited_at IS NOT NULL"""
        )
    if entity_type == "organization":
        branches.append(
            """SELECT 'partner-request:' || p.from_org_uuid::text || ':' || p.to_org_uuid::text,
            'partner_request', p.created_at AT TIME ZONE :tz, NULL, p.status,
            'partner-request:' || p.from_org_uuid::text || ':' || p.to_org_uuid::text,
            NULL, NULL, NULL, 'Partneranfrage erfasst', NULL, NULL, NULL
            FROM uranus.organization_partner_request p
            WHERE (p.from_org_uuid=:entity_uuid OR p.to_org_uuid=:entity_uuid)
              AND p.created_at IS NOT NULL"""
        )
    cursor_where = ""
    if cursor is not None:
        cursor_where = "WHERE occurred_at<:cursor_at OR (occurred_at=:cursor_at AND id<:cursor_id)"
    return f"""SELECT * FROM ({" UNION ALL ".join(branches)}) source_events
        {cursor_where}
        ORDER BY occurred_at DESC,id COLLATE \"C\" DESC LIMIT :limit"""


def admin_events_sql(cursor: TimelineCursor | None) -> str:
    cursor_where = ""
    if cursor is not None:
        cursor_where = "WHERE occurred_at<:cursor_at OR (occurred_at=:cursor_at AND id<:cursor_id)"
    return f"""SELECT * FROM ({ADMIN_EVENTS}) admin_events
        {cursor_where}
        ORDER BY occurred_at DESC,id COLLATE \"C\" DESC LIMIT :limit"""


def title(kind: str, status: str | None) -> str:
    fixed = {
        "source_created": "Quelldatensatz angelegt",
        "source_updated": "Quelldatensatz geändert",
        "finding_detected": "Qualitätsproblem erkannt",
        "finding_reviewed": "Befund geprüft",
        "finding_reopened": "Qualitätsproblem erneut aufgetreten",
        "finding_resolved": "Qualitätsproblem behoben",
        "mark_created": "Markierung hinzugefügt",
        "mark_updated": "Markierung geändert",
        "mark_completed": "Markierung erledigt",
        "mark_reopened": "Markierung wieder geöffnet",
        "assignment_created": "Aufgabe zugewiesen",
        "assignment_updated": "Zuweisung aktualisiert",
        "assignment_snoozed": "Wiedervorlage gesetzt",
        "assignment_unsnoozed": "Wiedervorlage aufgehoben",
        "assignment_completed": "Aufgabe erledigt",
        "assignment_reopened": "Aufgabe wieder geöffnet",
        "assignment_cancelled": "Zuweisung aufgehoben",
        "notification_delivery": "Benachrichtigung",
        "url_check": "URL-Prüfung",
        "geocode_request": "Standortprüfung",
        "geocode_result": "Geocoding-Ergebnis",
        "team_invitation": "Teameinladung",
        "partner_request": "Partneranfrage",
    }
    value = fixed[kind]
    if kind == "notification_delivery" and status == "sent":
        return "Benachrichtigung versendet"
    if kind == "notification_delivery" and status in {"failed", "permanent_failure"}:
        return "Benachrichtigung fehlgeschlagen"
    return value


def href(row: dict[str, Any], entity_type: TimelineEntityType, entity_key: str) -> str | None:
    resource = row["resource_id"]
    kind = row["kind"]
    if kind.startswith("finding_"):
        return "/findings?" + urlencode(
            {
                "mode": "persisted",
                "entity_type": entity_type,
                "entity_key": entity_key,
                "rule": row["rule"],
            }
        )
    if kind.startswith("mark_"):
        return f"/marks/{resource}"
    if kind == "notification_delivery":
        return f"/notifications/deliveries/{resource}"
    if kind.startswith("geocode_"):
        return f"/geocoding/{resource}"
    if kind == "team_invitation":
        return "/queues/team_invitations?" + urlencode({"entity_key": resource})
    if kind == "partner_request":
        return "/queues/partner_requests?" + urlencode({"entity_key": resource})
    return None


def item(row: dict[str, Any], entity_type: TimelineEntityType, entity_key: str) -> TimelineItem:
    return TimelineItem(
        id=row["id"],
        kind=row["kind"],
        occurred_at=row["occurred_at"],
        title=title(row["kind"], row["status"]),
        summary=row["summary"],
        actor=row["actor"],
        href=href(row, entity_type, entity_key),
        metadata=TimelineMetadata(
            status=row["status"],
            severity=row["severity"],
            rule=row["rule"],
            field=row["field"],
            resource_id=row["resource_id"],
            generation=row["generation"],
            score=row["score"],
            http_status=row["http_status"],
        ),
    )


async def timeline_page(
    source: AsyncConnection,
    admin: AsyncConnection,
    settings: Settings,
    entity_type: TimelineEntityType,
    entity_key: UUID,
    filters: TimelineFilters,
    now: datetime,
) -> TimelinePage:
    table, alias = SOURCE_TABLES[entity_type]
    exists = (
        await source.execute(
            text(f"SELECT EXISTS(SELECT 1 FROM {table} {alias} WHERE {alias}.uuid=:key)"),
            {"key": entity_key},
        )
    ).scalar_one()
    if not exists:
        raise APIError(404, "record_not_found", "Record not found.")
    entity_key_text = str(entity_key)
    cursor_scope = scope(
        filters,
        entity_type=entity_type,
        entity_key=entity_key_text,
        page_size=filters.page_size,
    )
    cursor = decode(filters.cursor, TimelineCursor, cursor_scope) if filters.cursor else None
    params: dict[str, Any] = {
        "entity_type": entity_type,
        "entity_key": entity_key_text,
        "entity_uuid": entity_key,
        "tz": require_timezone(settings),
        "admin_tz": settings.admin_timezone,
        "limit": filters.page_size + 1,
    }
    if cursor:
        params.update(cursor_at=cursor.occurred_at, cursor_id=cursor.id)
    source_rows = (
        await source.execute(text(source_events_sql(entity_type, cursor)), params)
    ).mappings()
    admin_rows = (await admin.execute(text(admin_events_sql(cursor)), params)).mappings()
    rows = [dict(row) for row in source_rows] + [dict(row) for row in admin_rows]
    rows.sort(key=lambda row: (row["occurred_at"], row["id"]), reverse=True)
    has_more = len(rows) > filters.page_size
    selected = rows[: filters.page_size]
    next_cursor = None
    if has_more and selected:
        last = selected[-1]
        next_cursor = encode(
            TimelineCursor(scope=cursor_scope, occurred_at=last["occurred_at"], id=last["id"])
        )
    return TimelinePage(
        entity_type=entity_type,
        entity_key=entity_key_text,
        items=[item(row, entity_type, entity_key_text) for row in selected],
        cursor_pagination=CursorPagination(
            page_size=filters.page_size, next_cursor=next_cursor, has_more=has_more
        ),
        observed_at=now,
    )
