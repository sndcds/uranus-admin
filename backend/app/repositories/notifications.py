"""Admin-only persistence, short per-organization planning transactions and leased claims."""

from datetime import datetime, time, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from app.admin_tables import notification as n
from app.admin_tables import notification_delivery as d
from app.admin_tables import notification_delivery_item as di
from app.config import Settings
from app.schemas.notifications import NotificationConfig, NotificationPayload
from app.services.notifications.batching import batches, content_version
from app.services.notifications.candidates import Candidate
from app.services.notifications.rendering import render


async def advisory(admin: AsyncConnection, key: str) -> None:
    await admin.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": "notifications:" + key},
    )


def local_day(now: datetime, timezone: str) -> tuple[datetime, datetime]:
    local = now.astimezone(ZoneInfo(timezone))
    start = datetime.combine(local.date(), time.min, local.tzinfo)
    end = datetime.combine(local.date() + timedelta(days=1), time.min, local.tzinfo)
    return start, end


async def synchronize(
    admin: AsyncConnection,
    organization_id: UUID,
    candidates: list[Candidate],
    config: NotificationConfig | None,
    settings: Settings,
    now: datetime,
    *,
    capability: bool = True,
) -> int:
    queued = 0
    async with admin.begin():
        await advisory(admin, str(organization_id))
        old = {
            r["dedupe_key"]: dict(r)
            for r in (
                await admin.execute(select(n).where(n.c.organization_id == organization_id))
            ).mappings()
        }
        seen = set()
        for item in candidates:
            seen.add(item.dedupe_key)
            existing = old.get(item.dedupe_key)
            # Don't create a historical notification for every irrelevant source entity.
            if not existing and item.status != "active":
                continue
            payload = item.payload.model_dump(mode="json")
            if existing:
                payload["episode"] = existing["payload"].get("episode", 1) + int(
                    existing["status"] in {"resolved", "expired"}
                    and item.status in {"active", "suppressed"}
                )
            values = dict(
                id=existing["id"] if existing else uuid4(),
                notification_type=item.notification_type,
                organization_id=organization_id,
                entity_type=payload["entity_type"],
                entity_key=payload["entity_key"],
                entity_name=payload["entity_name"],
                finding_id=payload["finding_id"],
                rule=payload["rule"],
                dedupe_key=item.dedupe_key,
                status=item.status,
                payload=payload,
                first_detected_at=existing["first_detected_at"] if existing else now,
                last_detected_at=now
                if item.status in {"active", "suppressed"} or not existing
                else existing["last_detected_at"],
                resolved_at=(existing.get("resolved_at") or now)
                if item.status == "resolved" and existing
                else now
                if item.status == "resolved"
                else None,
                expired_at=(existing.get("expired_at") or now)
                if item.status == "expired" and existing
                else now
                if item.status == "expired"
                else None,
                created_at=existing["created_at"] if existing else now,
                updated_at=now,
            )
            await admin.execute(
                insert(n)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[n.c.dedupe_key],
                    set_={
                        k: v
                        for k, v in values.items()
                        if k not in {"id", "created_at", "first_detected_at"}
                    },
                )
            )
        for key, row in old.items():
            if key not in seen and row["status"] not in {"resolved", "expired"}:
                status = (
                    "suppressed"
                    if not capability or config is None
                    else "resolved"
                    if row["notification_type"] == "quality_finding"
                    else "expired"
                )
                await admin.execute(
                    update(n)
                    .where(n.c.id == row["id"])
                    .values(
                        status=status,
                        updated_at=now,
                        resolved_at=now if status == "resolved" else None,
                        expired_at=now if status == "expired" else None,
                    )
                )
        rows = [
            dict(r)
            for r in (
                await admin.execute(select(n).where(n.c.organization_id == organization_id))
            ).mappings()
        ]
        history = [
            dict(r)
            for r in (
                await admin.execute(
                    select(d)
                    .where(d.c.organization_id == organization_id)
                    .order_by(d.c.created_at.desc())
                )
            ).mappings()
        ]
        # Cancel stale queued/retry intents, including removed/disabled recipients. Never
        # mutate historical mail or a currently leased external operation.
        for delivery in history:
            if delivery["status"] in {"queued", "failed"} and not valid_intent(
                delivery, rows, config
            ):
                await admin.execute(
                    update(d)
                    .where(d.c.id == delivery["id"])
                    .values(status="cancelled", updated_at=now)
                )
                delivery["status"] = "cancelled"
        if not config or not settings.notifications_delivery_enabled:
            return queued
        outstanding = {
            (r["recipient"].casefold(), id_)
            for r in history
            if r["status"] in {"queued", "failed", "sending"}
            for id_ in r["snapshot"]["ids"]
        }
        for recipient in config.recipients:
            if not recipient.enabled:
                continue
            for batch in batches(rows, history, recipient, config, now):
                if any(
                    (batch["recipient"].casefold(), id_) in outstanding
                    for id_ in batch["snapshot"]["ids"]
                ):
                    continue
                preview = render(
                    [NotificationPayload.model_validate(p) for p in batch["snapshot"]["payloads"]],
                    batch["locale"],
                    settings,
                )
                batch["snapshot"]["mail"] = preview.model_dump(mode="json")
                id_ = uuid4()
                created = (
                    await admin.execute(
                        insert(d)
                        .values(
                            id=id_,
                            organization_id=organization_id,
                            status="queued",
                            subject=preview.subject,
                            queued_at=now,
                            next_attempt_at=now,
                            created_at=now,
                            updated_at=now,
                            **batch,
                        )
                        .on_conflict_do_nothing()
                        .returning(d.c.id)
                    )
                ).scalar_one_or_none()
                if created:
                    queued += 1
                    await admin.execute(
                        insert(di),
                        [
                            {"delivery_id": id_, "notification_id": UUID(key)}
                            for key in batch["snapshot"]["ids"]
                        ],
                    )

    return queued


def valid_intent(
    delivery: dict[str, Any], rows: list[dict[str, Any]], config: NotificationConfig | None
) -> bool:
    if config is None or not any(
        r.enabled
        and str(r.email).casefold() == delivery["recipient"].casefold()
        and r.locale == delivery["locale"]
        for r in config.recipients
    ):
        return False
    items = [
        r for r in rows if str(r["id"]) in delivery["snapshot"]["ids"] and r["status"] == "active"
    ]
    if delivery["delivery_kind"] == "digest" and not delivery.get("retry_of_delivery_id"):
        items = [
            r
            for r in rows
            if r["notification_type"] == "quality_finding" and r["status"] == "active"
        ]
    return (
        len(items) == len(delivery["snapshot"]["ids"])
        and content_version(items) == delivery["snapshot"]["version"]
    )


async def claim(admin: AsyncConnection, settings: Settings, now: datetime) -> dict[str, Any] | None:
    if not settings.notifications_delivery_enabled:
        return None
    async with admin.begin():
        # One short claim critical section also serializes recipient budget reservations
        # across organizations. SKIP LOCKED avoids waiting on a delivery's final commit.
        await advisory(admin, "claim")
        rows = (
            (
                await admin.execute(
                    select(d)
                    .where(
                        or_(
                            (d.c.status.in_(["queued", "failed"])) & (d.c.next_attempt_at <= now),
                            (d.c.status == "sending") & (d.c.lease_until <= now),
                        )
                    )
                    .order_by(
                        case((d.c.delivery_kind == "digest", 0), else_=1).desc(),
                        d.c.snapshot["payloads"][0]["stage"].as_integer().desc(),
                        d.c.queued_at,
                        d.c.id,
                    )
                    .limit(100)
                    .with_for_update(skip_locked=True)
                )
            )
            .mappings()
            .all()
        )
        start, end = local_day(now, settings.admin_timezone)
        for row in rows:
            if row["attempt_count"] >= 5:
                await admin.execute(
                    update(d)
                    .where(d.c.id == row["id"])
                    .values(
                        status="permanent_failure",
                        last_error="attempt_limit",
                        worker_id=None,
                        lease_until=None,
                        updated_at=now,
                    )
                )
                continue
            # In-flight reservations count; ambiguous expired leases count by sending_at
            # too, conservatively preserving the daily cap after a process crash.
            counted = or_(
                (d.c.status == "sent") & (d.c.sent_at >= start) & (d.c.sent_at < end),
                (d.c.status == "sending") & ((d.c.lease_until > now) | (d.c.sending_at >= start)),
            )
            productive = (
                select(func.count())
                .select_from(d)
                .where(
                    func.lower(d.c.recipient) == row["recipient"].lower(),
                    d.c.delivery_kind != "test",
                    d.c.id != row["id"],
                    counted,
                )
            )
            count = (await admin.execute(productive)).scalar_one()
            quality = row["delivery_kind"] == "digest"
            digest_count = (
                (
                    await admin.execute(
                        productive.where(
                            d.c.organization_id == row["organization_id"],
                            d.c.delivery_kind == "digest",
                        )
                    )
                ).scalar_one()
                if quality
                else 0
            )
            due = (
                end
                if count >= settings.notification_max_emails_per_recipient_per_day or digest_count
                else now
            )
            if (
                quality
                and now.astimezone(ZoneInfo(settings.admin_timezone)).hour
                < settings.notification_quality_start_hour
            ):
                due = max(due, start + timedelta(hours=settings.notification_quality_start_hour))
            if due > now:
                await admin.execute(
                    update(d)
                    .where(d.c.id == row["id"])
                    .values(
                        status="failed" if row["attempt_count"] else "queued",
                        next_attempt_at=due,
                        worker_id=None,
                        lease_until=None,
                        updated_at=now,
                    )
                )
                continue
            worker = uuid4()
            values = dict(
                status="sending",
                worker_id=worker,
                lease_until=now + timedelta(seconds=settings.notification_lease_seconds),
                sending_at=now,
                attempt_count=row["attempt_count"] + 1,
                updated_at=now,
            )
            await admin.execute(update(d).where(d.c.id == row["id"]).values(**values))
            return {**dict(row), **values}
    return None
