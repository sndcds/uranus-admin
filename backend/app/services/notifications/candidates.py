"""Fresh source evidence plus persisted human review; no source writes."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlencode
from uuid import UUID
from zoneinfo import ZoneInfo

from app.config import Settings
from app.repositories.quality_sources import Sources
from app.schemas.notifications import (
    NotificationConfig,
    NotificationPayload,
    NotificationStatus,
    NotificationType,
)
from app.services.notifications.actions import RecipientActions
from app.services.notifications.policy import EXTERNAL_POLICY, SEVERITY, next_date, stage
from app.services.quality.core import QualityContext, evaluate_core


@dataclass
class Candidate:
    organization_id: UUID
    notification_type: NotificationType
    dedupe_key: str
    status: NotificationStatus
    payload: NotificationPayload


def detect(
    sources: Sources,
    configs: dict[UUID, NotificationConfig],
    reviews: dict[str, str],
    settings: Settings,
    now: datetime,
) -> list[Candidate]:
    context = QualityContext(sources, settings, now)
    organizations = sources.index("organization")
    actions = RecipientActions(sources, settings)
    local = now.astimezone(ZoneInfo(settings.event_timezone))
    result = []
    for event in sources.rows["event"]:
        org = organizations.get(str(event["org_uuid"]))
        if org is None:
            continue
        org_id = UUID(str(org["uuid"]))
        config = configs.get(org_id)
        enabled = bool(
            config
            and config.events.unpublished_upcoming_events.enabled
            and any(r.enabled for r in config.recipients)
        )
        date = next_date(context.dates_by_event.get(str(event["uuid"]), []), local)
        days = (date["start_date"] - local.date()).days if date else None
        status: NotificationStatus
        if event["release_status"] in {"released", "rescheduled"}:
            status = "resolved"
        elif event["release_status"] not in {"draft", "review"} or date is None:
            status = "expired"
        elif (
            not enabled
            or not config
            or days is None
            or days > config.events.unpublished_upcoming_events.days_before
        ):
            status = "suppressed"
        else:
            status = "active"
        current_stage = stage(days, settings) if days is not None else 0
        result.append(
            Candidate(
                org_id,
                "unpublished_upcoming_event",
                f"unpublished_upcoming_event:{org_id}:{event['uuid']}",
                status,
                NotificationPayload(
                    organization_name=org["name"],
                    entity_name=event["name"],
                    entity_type="event",
                    entity_key=str(event["uuid"]),
                    internal_action_path=f"/events/{event['uuid']}",
                    external_action_url=actions.url("event", str(event["uuid"]), org_id),
                    event_status=event["release_status"]
                    if event["release_status"] in {"draft", "review"}
                    else None,
                    next_date=date["start_date"].isoformat() if date else None,
                    days_until=days,
                    stage=current_stage,
                    priority="urgent"
                    if current_stage == 3
                    else "important"
                    if current_stage == 2
                    else "improvement",
                ),
            )
        )
    for rule, policy in EXTERNAL_POLICY.items():
        evaluated = evaluate_core(rule, sources, settings, now, context)
        if not evaluated.success:
            raise RuntimeError("Incomplete notification evidence")
        for f in evaluated.findings:
            if f.organization_id is None or f.entity_type not in policy.entities:
                continue
            config = configs.get(f.organization_id)
            enabled = bool(
                config
                and config.events.quality_findings.enabled
                and any(r.enabled for r in config.recipients)
                and SEVERITY[f.severity]
                >= SEVERITY[config.events.quality_findings.minimum_severity]
            )
            flags = sorted(f.priority_reasons)
            result.append(
                Candidate(
                    f.organization_id,
                    "quality_finding",
                    f"quality_finding:{f.organization_id}:{f.id}",
                    "active" if enabled and reviews.get(f.id) == "open" else "suppressed",
                    NotificationPayload(
                        organization_name=f.organization_name or "",
                        entity_name=f.entity_name,
                        entity_type=f.entity_type,
                        entity_key=f.entity_key,
                        external_action_url=actions.url(
                            f.entity_type, f.entity_key, f.organization_id
                        ),
                        internal_action_path="/findings?"
                        + urlencode(
                            {
                                "mode": "persisted",
                                "organization_id": str(f.organization_id),
                                "entity_type": f.entity_type,
                                "entity_key": f.entity_key,
                            }
                        ),
                        rule=f.rule,
                        finding_id=f.id,
                        severity=f.severity,
                        field=f.field,
                        relevance=flags,
                        priority="urgent"
                        if "published_soon" in flags
                        else "important"
                        if "upcoming_dates" in flags
                        else "improvement",
                    ),
                )
            )
    return result


def semantic_payload(payload: dict[str, Any]) -> dict[str, Any]:
    # Countdown/observation time alone never resends a digest or event email.
    return {key: value for key, value in payload.items() if key != "days_until"}
