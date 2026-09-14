import hashlib
import json
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.errors import APIError
from app.repositories.queues import queue_rows
from app.schemas.action import Action
from app.schemas.finding import Pagination, Severity
from app.schemas.queues import QueueFilters, QueueItem, QueueKind, QueuePage
from app.services.quality.core import RuleResult, make_finding

QUEUE_RULES = (
    "partner_self_request",
    "partner_missing_organization",
    "partner_missing_user",
    "partner_unknown_status",
    "partner_long_pending",
    "partner_accepted_without_grant",
    "team_invitation_old",
    "user_activation_old",
)


def map_queue(kind: QueueKind, row: dict[str, Any], settings: Settings, now: datetime) -> QueueItem:
    if settings.uranus_timestamp_timezone is None:
        raise APIError(503, "source_timezone_unconfigured", "Source timezone must be configured.")
    tz = ZoneInfo(settings.uranus_timestamp_timezone)
    created = row["created_at"].replace(tzinfo=tz)
    invited = row.get("invited_at")
    invited = invited.replace(tzinfo=tz) if invited else None
    basis = invited if kind == "team_invitations" else created
    age = (now - basis).days if basis and basis <= now else None
    checks: list[str] = []
    if kind == "partner_requests":
        key = f"partner-request:{row['from_org_uuid']}:{row['to_org_uuid']}"
        if row["from_org_uuid"] == row["to_org_uuid"]:
            checks.append("partner_self_request")
        if row["from_name"] is None or row["to_name"] is None:
            checks.append("partner_missing_organization")
        if not row["user_exists"]:
            checks.append("partner_missing_user")
        if row["status"] not in {"pending", "accepted"}:
            checks.append("partner_unknown_status")
        if row["status"] == "pending" and created < now - timedelta(days=settings.pending_age_days):
            checks.append("partner_long_pending")
        if row["status"] == "accepted" and not row["grant_exists"]:
            checks.append("partner_accepted_without_grant")
        return QueueItem(
            entity_key=key,
            organization_id=row["from_org_uuid"],
            organization_name=row["from_name"],
            from_organization_id=row["from_org_uuid"],
            from_organization_name=row["from_name"],
            to_organization_id=row["to_org_uuid"],
            to_organization_name=row["to_name"],
            user_id=row["user_id"],
            user_name=row["user_name"],
            status=row["status"],
            created_at=created,
            age_days=age,
            age_basis="created_at",
            checks=checks,
            action=Action(route=kind, entity_key=key),
        )
    if kind == "team_invitations":
        key = f"membership:{row['org_uuid']}:{row['user_id']}"
        if (
            not row["has_joined"]
            and invited
            and invited < now - timedelta(days=settings.pending_age_days)
        ):
            checks.append("team_invitation_old")
        return QueueItem(
            entity_key=key,
            organization_id=row["org_uuid"],
            organization_name=row["organization_name"],
            user_id=row["user_id"],
            user_name=row["user_name"],
            status="joined" if row["has_joined"] else "invited",
            created_at=created,
            invited_at=invited,
            has_joined=row["has_joined"],
            age_days=age,
            age_basis="invited_at",
            checks=checks,
            action=Action(route=kind, entity_key=key),
        )
    key = str(row["user_id"])
    if not row["is_active"] and created < now - timedelta(days=settings.activation_age_days):
        checks.append("user_activation_old")
    return QueueItem(
        entity_key=key,
        user_id=row["user_id"],
        user_name=row["user_name"],
        status="active" if row["is_active"] else "inactive",
        created_at=created,
        age_days=age,
        age_basis="created_at",
        checks=checks,
        action=Action(route=kind, entity_key=key),
    )


async def get_queue(
    connection: AsyncConnection,
    settings: Settings,
    kind: QueueKind,
    filters: QueueFilters,
    now: datetime,
) -> QueuePage:
    rows = await queue_rows(connection, kind)
    items = []
    for row in rows:
        item = map_queue(kind, row, settings, now)
        if item.status in {"joined", "active"}:
            continue
        if filters.organization_id and filters.organization_id not in {
            item.organization_id,
            item.to_organization_id,
            *row.get("organizations", []),
        }:
            continue
        if filters.entity_key and filters.entity_key != item.entity_key:
            continue
        if filters.status and filters.status != item.status:
            continue
        if filters.min_age_days is not None and (
            item.age_days is None or item.age_days < filters.min_age_days
        ):
            continue
        items.append(item)
    items.sort(key=lambda item: (item.age_days is None, -(item.age_days or 0), item.entity_key))
    total = len(items)
    start = (filters.page - 1) * filters.page_size
    return QueuePage(
        kind=kind,
        items=items[start : start + filters.page_size],
        observed_at=now,
        pagination=Pagination(
            page=filters.page,
            page_size=filters.page_size,
            total=total,
            pages=(total + filters.page_size - 1) // filters.page_size,
        ),
    )


async def queue_findings(
    connection: AsyncConnection, settings: Settings, now: datetime
) -> list[RuleResult]:
    results = {rule: RuleResult(rule) for rule in QUEUE_RULES}
    for kind, entity_type, rules in [
        ("partner_requests", "partner_request", QUEUE_RULES[:6]),
        ("team_invitations", "team_membership", ("team_invitation_old",)),
        ("user_activation", "user", ("user_activation_old",)),
    ]:
        rows = await queue_rows(connection, kind)  # type: ignore[arg-type]
        for row in rows:
            item = map_queue(kind, row, settings, now)  # type: ignore[arg-type]
            for rule in rules:
                results[rule].covered.add((entity_type, item.entity_key))
            for rule in item.checks:
                severity = (
                    Severity.info
                    if rule in {"partner_accepted_without_grant", "user_activation_old"}
                    else Severity.warning
                )
                if rule in {
                    "partner_self_request",
                    "partner_missing_organization",
                    "partner_missing_user",
                }:
                    severity = Severity.error
                finding = make_finding(
                    rule,
                    entity_type,
                    item.entity_key,
                    "status",
                    rule.replace("_", " "),
                    now,
                    severity=severity,
                    name=item.user_name,
                    organization={"uuid": item.organization_id, "name": item.organization_name}
                    if item.organization_id
                    else None,
                    metadata={
                        "age_days": item.age_days,
                        "age_basis": item.age_basis,
                        "source_fingerprint": hashlib.sha256(
                            json.dumps(row, sort_keys=True, default=str).encode()
                        ).hexdigest(),
                    },
                )
                finding.action = item.action
                results[rule].findings.append(finding)
    return list(results.values())
