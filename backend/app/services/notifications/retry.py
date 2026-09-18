"""Explicit retry intent, never SMTP or mutation of a historical delivery."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.admin_tables import notification as n
from app.admin_tables import notification_delivery as d
from app.admin_tables import notification_delivery_item as di
from app.config import Settings
from app.errors import APIError
from app.repositories.notifications import advisory, valid_intent
from app.schemas.notifications import NotificationPayload, NotificationRetryResponse
from app.services.notifications.batching import content_version, fingerprint
from app.services.notifications.rendering import render
from app.services.notifications.state import collect, refresh_rows


async def enqueue_retry(
    admin: AsyncConnection,
    source: AsyncEngine,
    delivery_id: UUID,
    settings: Settings,
    now: datetime,
) -> NotificationRetryResponse:
    async with admin.begin():
        old = (await admin.execute(select(d).where(d.c.id == delivery_id))).mappings().one_or_none()
        if old is None:
            raise APIError(404, "notification_delivery_not_found", "Delivery not found.")
        # Same lock/order as normal planning. No competing planner can insert an
        # overlapping intent between our fresh validation and atomic queue insertion.
        await advisory(admin, str(old["organization_id"]))
        old = (
            (await admin.execute(select(d).where(d.c.id == delivery_id).with_for_update()))
            .mappings()
            .one()
        )
        if old["status"] != "permanent_failure" or old["delivery_kind"] == "test":
            raise APIError(409, "notification_retry_not_allowed", "Delivery cannot be retried.")
        child = (
            await admin.execute(
                select(d.c.status).where(
                    d.c.retry_of_delivery_id == delivery_id, d.c.status != "cancelled"
                )
            )
        ).scalar_one_or_none()
        if child is not None:
            code = (
                "notification_retry_already_queued"
                if child in {"queued", "sending", "failed"}
                else "notification_retry_not_allowed"
            )
            raise APIError(409, code, "Retry the latest eligible delivery in the chain.")
        available, configs, fresh = await collect(
            source, admin.engine, settings, now, old["organization_id"]
        )
        config = configs.get(old["organization_id"])
        recipient = (
            next(
                (
                    r
                    for r in config.recipients
                    if r.enabled and str(r.email).casefold() == old["recipient"].casefold()
                ),
                None,
            )
            if config
            else None
        )
        if not available or recipient is None:
            raise APIError(409, "notification_retry_obsolete", "Recipient or source unavailable.")
        original = [
            dict(row)
            for row in (
                await admin.execute(
                    select(n)
                    .join(di, di.c.notification_id == n.c.id)
                    .where(
                        di.c.delivery_id == delivery_id,
                        n.c.organization_id == old["organization_id"],
                        n.c.status == "active",
                    )
                    .order_by(n.c.id)
                )
            ).mappings()
        ]
        items = [row for row in refresh_rows(original, fresh) if row["status"] == "active"]
        if not items:
            raise APIError(409, "notification_retry_obsolete", "No eligible original items remain.")
        ids = [row["id"] for row in items]
        overlap = (
            await admin.execute(
                select(d.c.id)
                .join(di, di.c.delivery_id == d.c.id)
                .where(
                    d.c.organization_id == old["organization_id"],
                    func.lower(d.c.recipient) == str(recipient.email).lower(),
                    d.c.status.in_(["queued", "sending", "failed"]),
                    di.c.notification_id.in_(ids),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if overlap is not None:
            raise APIError(409, "notification_retry_already_queued", "An overlapping retry exists.")
        payloads = [row["payload"] for row in items]
        version = content_version(items)
        intent: dict[str, Any] = {
            "retry_of_delivery_id": delivery_id,
            "recipient": str(recipient.email),
            "locale": recipient.locale,
            "delivery_kind": old["delivery_kind"],
            "snapshot": {
                "ids": [str(id_) for id_ in ids],
                "payloads": payloads,
                "version": version,
            },
        }
        if not valid_intent(intent, items, config):
            raise APIError(409, "notification_retry_obsolete", "Retry intent is obsolete.")
        preview = render(
            [NotificationPayload.model_validate(p) for p in payloads], recipient.locale, settings
        )
        intent["snapshot"]["mail"] = preview.model_dump(mode="json")
        new_id = uuid4()
        await admin.execute(
            insert(d).values(
                id=new_id,
                organization_id=old["organization_id"],
                status="queued",
                subject=preview.subject,
                attempt_count=0,
                queued_at=now,
                next_attempt_at=now,
                created_at=now,
                updated_at=now,
                message_fingerprint=fingerprint({"manual_retry_of": str(delivery_id)}),
                **intent,
            )
        )
        await admin.execute(
            insert(di), [{"delivery_id": new_id, "notification_id": id_} for id_ in ids]
        )
        return NotificationRetryResponse(delivery_id=new_id, retry_of_delivery_id=delivery_id)
