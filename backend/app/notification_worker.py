"""Durable organization email worker. Safe by default; --once performs one bounded run."""

import argparse
import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.admin_database import assert_admin_boundary, create_admin_engine
from app.admin_tables import notification
from app.admin_tables import notification_delivery as d
from app.config import Settings
from app.database import create_engine
from app.logging import configure_logging
from app.repositories.notifications import claim, synchronize, valid_intent
from app.schemas.notifications import NotificationPayload
from app.services.notifications.candidates import Candidate
from app.services.notifications.delivery import SMTPTransport, Transport, finish, message
from app.services.notifications.rendering import render
from app.services.notifications.state import collect, refresh_rows
from app.storage_preflight import RUNTIME_GRANTS, check_grants, check_schema

LOG = logging.getLogger("admin.notifications")


def utcnow() -> datetime:
    return datetime.now(UTC)


async def work_once(
    source: AsyncEngine,
    admin: AsyncEngine,
    settings: Settings,
    transport: Transport | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> dict[str, int]:
    counts = {
        "candidates_detected": 0,
        "deliveries_queued": 0,
        "deliveries_sent": 0,
        "deliveries_failed": 0,
        "deliveries_suppressed": 0,
    }
    async with admin.connect() as writer:
        async with writer.begin():
            await assert_admin_boundary(writer)
            await check_schema(writer)
            await check_grants(writer, RUNTIME_GRANTS)
        capability, configs, candidates = await collect(source, admin, settings, clock())
        grouped: dict[UUID, list[Candidate]] = defaultdict(list)
        for candidate in candidates:
            grouped[candidate.organization_id].append(candidate)
            counts["candidates_detected"] += candidate.status == "active"
        async with writer.begin():
            known = set(
                (await writer.execute(select(notification.c.organization_id).distinct())).scalars()
            )
        for org in known | set(grouped) | set(configs):
            counts["deliveries_queued"] += await synchronize(
                writer,
                org,
                grouped[org],
                configs.get(org),
                settings,
                clock(),
                capability=capability,
            )
        if not settings.notifications_delivery_enabled or not capability:
            LOG.info("notification_run", extra=counts)
            return counts
        transport = transport or SMTPTransport(settings)
        # Bound external work in one invocation. Remaining durable rows stay queued.
        for _ in range(100):
            delivery = await claim(writer, settings, clock())
            if delivery is None:
                break
            # Revalidate after claiming, before the external effect. Changes to source,
            # recipient, locale, review or relevance cancel an obsolete intent.
            try:
                available, fresh_configs, fresh = await collect(
                    source, admin, settings, clock(), delivery["organization_id"]
                )
                async with writer.begin():
                    rows = [
                        dict(r)
                        for r in (
                            await writer.execute(
                                select(notification).where(
                                    notification.c.organization_id == delivery["organization_id"]
                                )
                            )
                        ).mappings()
                    ]
                rows = refresh_rows(rows, fresh)
                valid = available and valid_intent(
                    delivery, rows, fresh_configs.get(delivery["organization_id"])
                )
                if not valid:
                    async with writer.begin():
                        await writer.execute(
                            update(d)
                            .where(d.c.id == delivery["id"], d.c.worker_id == delivery["worker_id"])
                            .values(
                                status="cancelled",
                                worker_id=None,
                                lease_until=None,
                                updated_at=clock(),
                            )
                        )
                    counts["deliveries_suppressed"] += 1
                    continue
                async with writer.begin():
                    renewed = await writer.execute(
                        update(d)
                        .where(
                            d.c.id == delivery["id"],
                            d.c.worker_id == delivery["worker_id"],
                            d.c.status == "sending",
                            d.c.lease_until > clock(),
                        )
                        .values(
                            lease_until=clock()
                            + timedelta(seconds=settings.notification_lease_seconds)
                        )
                    )
                    if renewed.rowcount != 1:
                        raise RuntimeError("Notification lease lost before SMTP")
                # A queued mail may have waited for a daily quota. Compose its relative
                # dates at first SMTP attempt, then freeze content for retries/audit.
                if delivery["attempt_count"] == 1:
                    by_id = {str(row["id"]): row for row in rows}
                    payloads = [by_id[key]["payload"] for key in delivery["snapshot"]["ids"]]
                    preview = render(
                        [NotificationPayload.model_validate(p) for p in payloads],
                        delivery["locale"],
                        settings,
                    )
                    snapshot = {
                        **delivery["snapshot"],
                        "payloads": payloads,
                        "mail": preview.model_dump(mode="json"),
                        "composed_at": clock().isoformat(),
                    }
                    async with writer.begin():
                        saved = await writer.execute(
                            update(d)
                            .where(
                                d.c.id == delivery["id"],
                                d.c.worker_id == delivery["worker_id"],
                                d.c.status == "sending",
                                d.c.lease_until > clock(),
                            )
                            .values(snapshot=snapshot, subject=preview.subject)
                        )
                        if saved.rowcount != 1:
                            raise RuntimeError("Notification lease lost before composition")
                    delivery["snapshot"] = snapshot
                # Heartbeat extends the claim during synchronous SMTP in a worker thread.
                stop = asyncio.Event()

                async def heartbeat(current: dict[str, Any], stop: asyncio.Event) -> None:
                    while not stop.is_set():
                        try:
                            await asyncio.wait_for(
                                stop.wait(), settings.notification_lease_seconds / 3
                            )
                        except TimeoutError:
                            async with admin.connect() as lease, lease.begin():
                                result = await lease.execute(
                                    update(d)
                                    .where(
                                        d.c.id == current["id"],
                                        d.c.worker_id == current["worker_id"],
                                        d.c.status == "sending",
                                        d.c.lease_until > clock(),
                                    )
                                    .values(
                                        lease_until=clock()
                                        + timedelta(seconds=settings.notification_lease_seconds)
                                    )
                                )
                                if result.rowcount != 1:
                                    raise RuntimeError("Notification lease lost") from None

                task = asyncio.create_task(heartbeat(delivery, stop))
                try:
                    await asyncio.to_thread(
                        transport.send, message(delivery, settings), delivery["recipient"]
                    )
                finally:
                    stop.set()
                    await task
                if await finish(writer, delivery, clock()):
                    counts["deliveries_sent"] += 1
            except Exception as exc:
                if writer.in_transaction():
                    await writer.rollback()
                await finish(writer, delivery, clock(), exc)
                counts["deliveries_failed"] += 1
                LOG.warning(
                    "notification_delivery_failed",
                    extra={"delivery_id": str(delivery["id"]), "error_type": type(exc).__name__},
                )
    LOG.info("notification_run", extra=counts)
    return counts


async def run(settings: Settings, once: bool = False) -> None:
    configure_logging(settings.log_level)
    source, admin = create_engine(settings), create_admin_engine(settings)
    if admin is None:
        await source.dispose()
        raise RuntimeError("Admin storage required")
    try:
        while True:
            try:
                await work_once(source, admin, settings)
            except Exception as exc:
                LOG.error("notification_worker_failed", extra={"error_type": type(exc).__name__})
                if once:
                    raise RuntimeError("Notification worker unavailable") from None
            if once:
                return
            await asyncio.sleep(settings.notification_worker_poll_seconds)
    finally:
        await source.dispose()
        await admin.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(Settings(), args.once))
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit(
            "Notification worker unavailable; check source, admin storage and grants."
        ) from None


if __name__ == "__main__":
    main()
