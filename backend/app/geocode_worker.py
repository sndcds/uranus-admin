"""Bounded, paced location suggestions. No domain writes; prefer hourly --once timer."""

import argparse
import asyncio
import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.admin_database import assert_admin_boundary, create_admin_engine
from app.admin_tables import geocode_request
from app.config import Settings
from app.database import create_engine
from app.errors import APIError
from app.logging import configure_logging
from app.repositories import geocode
from app.repositories.geocode_sources import PROJECTIONS, lookup_sources, source_rows
from app.schemas.geocode import GeocodeStatus
from app.services.geo.geocoding import candidates, query_inputs, result_status, source_fingerprint
from app.services.nominatim import NominatimClient
from app.storage_preflight import RUNTIME_GRANTS, check_grants, check_schema

logger = logging.getLogger("admin.geocode")
# Session advisory lock: one provider consumer across processes, released on connection
# loss. No admin transaction is held while pacing or doing HTTP. Row leases still fence
# manual retries and late completion and are independently recoverable.
WORKER_LOCK = 72619334011


async def current_sources(
    source: AsyncEngine, jobs: list[dict[str, Any]]
) -> dict[tuple[str, Any], dict[str, Any]]:
    async with source.connect() as reader, reader.begin():
        await reader.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        return await lookup_sources(reader, jobs)


async def work_once(
    source: AsyncEngine,
    admin: AsyncEngine,
    settings: Settings,
    provider: NominatimClient | None = None,
) -> dict[str, int]:
    provider = provider or NominatimClient(settings)
    counts = {
        key: 0
        for key in (
            "entities_scanned",
            "requests_synchronized",
            "requests_created",
            "requests_checked",
            "candidates_found",
            "ambiguous",
            "not_found",
            "failed",
            "stale",
            "insufficient_input",
        )
    }
    async with admin.connect() as coordinator:
        async with coordinator.begin():
            await assert_admin_boundary(coordinator)
            await check_schema(coordinator)
            await check_grants(coordinator, RUNTIME_GRANTS)
            locked = (
                await coordinator.execute(
                    text("SELECT pg_try_advisory_lock(:key)"), {"key": WORKER_LOCK}
                )
            ).scalar_one()
        if not locked:
            return counts
        try:
            # Reconcile existing requests, including deleted owners/points that appeared.
            after = None
            while True:
                async with coordinator.begin():
                    query = select(geocode_request).order_by(geocode_request.c.id).limit(500)
                    if after:
                        query = query.where(geocode_request.c.id > after)
                    jobs = [dict(row) for row in (await coordinator.execute(query)).mappings()]
                if not jobs:
                    break
                after = jobs[-1]["id"]
                sources = await current_sources(source, jobs)
                counts["stale"] += await geocode.mark_stale(
                    coordinator,
                    [
                        job["id"]
                        for job in jobs
                        if (row := sources.get((job["entity_type"], job["entity_key"]))) is None
                        or not row["point_missing"]
                    ],
                )
                counts["requests_synchronized"] += await geocode.synchronize(
                    coordinator, list(sources.values()), counts
                )
            # Read-only keyset batches: no full source materialization, no N+1 discovery.
            for kind in PROJECTIONS:
                after = None
                async with source.connect() as reader, reader.begin():
                    await reader.execute(
                        text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                    )
                    while True:
                        rows = await source_rows(reader, kind, after=after)
                        if not rows:
                            break
                        after = rows[-1]["entity_key"]
                        counts["entities_scanned"] += len(rows)
                        counts["requests_synchronized"] += await geocode.synchronize(
                            coordinator, rows, counts
                        )
            owner = uuid4()
            called = False
            for _ in range(settings.geocode_batch_size):
                job = await geocode.claim(coordinator, settings, owner)
                if job is None:
                    break
                logger.info("geocode_request_claimed", extra={"request_id": str(job["id"])})
                current = await current_sources(source, [job])
                row = current.get((job["entity_type"], job["entity_key"]))
                if row is None or not row["point_missing"]:
                    counts["stale"] += await geocode.mark_stale(coordinator, [job["id"]])
                    continue
                if source_fingerprint(row) != job["source_fingerprint"]:
                    await geocode.synchronize(coordinator, [row])
                    continue
                inputs = query_inputs(row)
                items = []
                status: GeocodeStatus = "insufficient_input"
                if inputs:
                    if called:
                        await asyncio.sleep(settings.geocode_request_interval_ms / 1000)
                    if not await geocode.begin_attempt(coordinator, job, owner, row, settings):
                        continue
                    called = True
                    try:
                        items = candidates(
                            row,
                            await provider.geocode_address(inputs),
                            settings.geocode_max_candidates,
                        )
                        status = result_status(items)
                    except APIError:
                        status = "failed"
                # A fresh source transaction prevents publishing a proposal for a changed
                # address/point observed during HTTP. Cross-DB reads remain observational.
                latest = (await current_sources(source, [job])).get(
                    (job["entity_type"], job["entity_key"])
                )
                if latest is None or not latest["point_missing"]:
                    counts["stale"] += await geocode.mark_stale(coordinator, [job["id"]])
                    continue
                if source_fingerprint(latest) != job["source_fingerprint"]:
                    await geocode.synchronize(coordinator, [latest])
                    continue
                if await geocode.finish(coordinator, settings, job, owner, status, items):
                    counts["requests_checked"] += 1
                    counts["candidates_found"] += len(items)
                    if status in counts:
                        counts[status] += 1
                    logger.info(
                        "geocode_" + status,
                        extra={"request_id": str(job["id"]), "candidate_count": len(items)},
                    )
        finally:
            async with coordinator.begin():
                await coordinator.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": WORKER_LOCK}
                )
    logger.info("geocode_run", extra=counts)
    return counts


async def run(settings: Settings, once: bool) -> None:
    source, admin = create_engine(settings), create_admin_engine(settings)
    if admin is None:
        await source.dispose()
        raise RuntimeError("Admin storage required")
    try:
        while True:
            await work_once(source, admin, settings)
            if once:
                return
            await asyncio.sleep(60)
    finally:
        await source.dispose()
        await admin.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        settings = Settings()
        configure_logging(settings.log_level)
        asyncio.run(run(settings, args.once))
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit(
            "Geocode worker unavailable; check storage, grants and migrations."
        ) from None


if __name__ == "__main__":
    main()
