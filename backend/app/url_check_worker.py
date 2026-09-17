"""Explicit standalone worker for durable, leased public URL observations (no HTTP lifetime)."""

import argparse
import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.admin_database import assert_admin_boundary, create_admin_engine
from app.admin_tables import finding, url_check
from app.config import Settings
from app.database import create_engine
from app.services.checks import LOCK_KEY, persist_results
from app.services.quality.core import URL_FIELDS, RuleResult, make_finding
from app.services.url_reachability import InvalidTarget, Observation, check_url, normalized_url
from app.storage_preflight import RUNTIME_GRANTS, check_grants, check_schema

RULE = "url_unreachable"
FAILURES = {"unreachable", "timeout", "dns_error", "tls_error"}
SOURCE_KEYS = {kind: "uuid" for kind in URL_FIELDS} | {"event_link": "id", "license": "key"}
SOURCE_URLS = " UNION ALL ".join(
    f"SELECT '{kind}' kind,{SOURCE_KEYS[kind]}::text key,'{field}' field,{field} url "
    f"FROM uranus.{kind} WHERE {field} IS NOT NULL AND btrim({field})<>''"
    for kind, fields in URL_FIELDS.items()
    for field in fields
)


def identity(kind: str, key: str, field: str) -> str:
    return hashlib.sha256(f"{kind}\0{key}\0{field}".encode()).hexdigest()


async def discover(admin: AsyncConnection, rows: list[dict[str, Any]]) -> list[str]:
    values = []
    for row in rows:
        try:
            url = normalized_url(row["url"].strip())
        except InvalidTarget:
            continue  # Syntax-only/private credential values are never copied into this store.
        values.append(
            dict(
                id=identity(row["kind"], row["key"], row["field"]),
                source_type=row["kind"],
                source_key=row["key"],
                field=row["field"],
                url=url,
            )
        )
    if not values:
        return []
    stmt = insert(url_check).values(values)
    async with admin.begin():
        await admin.execute(
            stmt.on_conflict_do_update(
                index_elements=[url_check.c.id],
                set_={
                    "url": stmt.excluded.url,
                    "status": "pending",
                    "last_checked_at": None,
                    "last_success_at": None,
                    "status_code": None,
                    "redirect_target": None,
                    "failure_type": None,
                    "failure_count": 0,
                    "next_check_at": func.clock_timestamp(),
                    "worker_id": None,
                    "lease_until": None,
                },
                where=url_check.c.url != stmt.excluded.url,
            )
        )
    return [value["id"] for value in values]


async def claim(admin: AsyncConnection, key: str, owner: UUID) -> dict[str, Any] | None:
    async with admin.begin():
        row = (
            (
                await admin.execute(
                    update(url_check)
                    .where(
                        url_check.c.id == key,
                        url_check.c.next_check_at <= func.clock_timestamp(),
                        (url_check.c.lease_until.is_(None))
                        | (url_check.c.lease_until < func.clock_timestamp()),
                    )
                    .values(
                        worker_id=owner,
                        lease_until=func.clock_timestamp() + text("interval '120 seconds'"),
                    )
                    .returning(url_check)
                )
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None


async def finish(
    admin: AsyncConnection,
    settings: Settings,
    job: dict[str, Any],
    owner: UUID,
    result: Observation,
) -> bool:
    now = datetime.now(UTC)
    async with admin.begin():
        # Same short persistence lock as review. Never held during DNS or HTTP.
        await admin.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
        current = (
            (
                await admin.execute(
                    select(url_check)
                    .where(
                        url_check.c.id == job["id"],
                        url_check.c.worker_id == owner,
                        url_check.c.url == job["url"],
                        url_check.c.lease_until > func.clock_timestamp(),
                    )
                    .with_for_update()
                )
            )
            .mappings()
            .first()
        )
        if current is None:
            return False
        failed = result.status in FAILURES
        failures = current["failure_count"] + 1 if failed else 0
        ttl = (
            settings.url_check_success_ttl_seconds
            if result.status == "reachable"
            else settings.url_check_failure_ttl_seconds
        )
        await admin.execute(
            update(url_check)
            .where(url_check.c.id == job["id"])
            .values(
                last_checked_at=now,
                last_success_at=now if result.status == "reachable" else current["last_success_at"],
                status=result.status,
                status_code=result.status_code,
                redirect_target=result.redirect_target,
                failure_type=result.failure_type,
                failure_count=failures,
                next_check_at=now + timedelta(seconds=ttl),
                worker_id=None,
                lease_until=None,
            )
        )
        item = make_finding(
            RULE,
            job["source_type"],
            job["source_key"],
            job["field"],
            "Öffentliche URL bei wiederholter Prüfung nicht erreichbar.",
            now,
            metadata={
                "failure_type": result.failure_type,
                "status_code": result.status_code,
                "url_fingerprint": hashlib.sha256(job["url"].encode()).hexdigest(),
            },
        )
        if failed and failures >= 2:
            # Empty coverage: a result for one URL must never resolve another field on the entity.
            await persist_results(admin, [RuleResult(RULE, [item], set())], now)
        elif result.status == "reachable":
            # Positive evidence only, scoped to this exact rule/entity/field identity.
            await admin.execute(
                update(finding)
                .where(finding.c.id == item.id, finding.c.status != "resolved")
                .values(status="resolved", resolved_at=now, last_seen_at=now)
            )
        return True


async def work_once(source: AsyncEngine, admin: AsyncEngine, settings: Settings) -> int:
    async with admin.connect() as setup, setup.begin():
        await assert_admin_boundary(setup)
        await check_schema(setup)
        await check_grants(setup, RUNTIME_GRANTS)
    owner = uuid4()
    processed = 0
    slots = asyncio.Semaphore(settings.url_check_concurrency)
    # One batch has at most 200 hosts; no unbounded persistent in-memory buckets.
    async with source.connect() as reader, reader.begin():
        await reader.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        after = ("", "", "")
        while processed < settings.url_check_batch_size:
            rows = [
                dict(row)
                for row in (
                    await reader.execute(
                        text(f"""
                SELECT * FROM ({SOURCE_URLS}) u
                WHERE (kind COLLATE "C",key COLLATE "C",field COLLATE "C") > (:kind,:key,:field)
                ORDER BY kind COLLATE "C",key COLLATE "C",field COLLATE "C" LIMIT 200
            """),
                        dict(zip(("kind", "key", "field"), after, strict=True)),
                    )
                ).mappings()
            ]
            if not rows:
                break
            after = tuple(rows[-1][key] for key in ("kind", "key", "field"))
            async with admin.connect() as connection:
                ids = await discover(connection, rows)
            host_locks: dict[str, asyncio.Lock] = {}
            hosts = {
                identity(row["kind"], row["key"], row["field"]): urlsplit(row["url"]).hostname or ""
                for row in rows
                if identity(row["kind"], row["key"], row["field"]) in ids
            }

            async def process(key: str, host: str, lock: asyncio.Lock) -> None:
                nonlocal processed
                async with slots, lock:
                    if processed >= settings.url_check_batch_size:
                        return
                    async with admin.connect() as connection:
                        job = await claim(connection, key, owner)
                    if job is None:
                        return
                    processed += 1
                    result = await check_url(job["url"])
                    async with admin.connect() as connection:
                        await finish(connection, settings, job, owner, result)
                    await asyncio.sleep(1)

            async with asyncio.TaskGroup() as tasks:
                for key in ids:
                    tasks.create_task(
                        process(key, hosts[key], host_locks.setdefault(hosts[key], asyncio.Lock()))
                    )
    return processed


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
        asyncio.run(run(Settings(), args.once))
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit("URL worker unavailable; check storage, grants and migrations.") from None


if __name__ == "__main__":
    main()
