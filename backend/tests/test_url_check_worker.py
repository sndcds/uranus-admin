from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update

from app.admin_tables import finding, url_check
from app.services.url_reachability import Observation
from app.url_check_worker import claim, discover, finish
from tests.conftest import uid

pytestmark = pytest.mark.integration


async def test_url_state_ttl_fencing_and_conservative_findings(admin_store, settings):
    rows = [dict(kind="venue", key=str(uid(20)), field="web_link", url="https://public.test")]
    key = (await discover(admin_store, rows))[0]
    owner = uuid4()
    job = await claim(admin_store, key, owner)
    assert job is not None
    assert await claim(admin_store, key, uuid4()) is None
    assert not await finish(admin_store, settings, job, uuid4(), Observation("reachable", 200))
    assert await finish(
        admin_store, settings, job, owner, Observation("timeout", failure_type="timeout")
    )
    async with admin_store.begin():
        assert not (await admin_store.execute(select(finding))).all()
        first = (await admin_store.execute(select(url_check))).mappings().one()
        assert first["last_checked_at"] is not None and first["last_success_at"] is None
        await admin_store.execute(
            update(url_check).values(next_check_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    job = await claim(admin_store, key, owner)
    await finish(admin_store, settings, job, owner, Observation("timeout", failure_type="timeout"))
    async with admin_store.begin():
        stored = (await admin_store.execute(select(finding))).mappings().one()
        assert stored["status"] == "open" and stored["severity"] == "warning"
        await admin_store.execute(
            update(finding).values(
                status="exception", exception_reason="Approved", reviewed_subject="admin:test"
            )
        )
        await admin_store.execute(
            update(url_check).values(next_check_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    job = await claim(admin_store, key, owner)
    await finish(admin_store, settings, job, owner, Observation("blocked", 403))
    async with admin_store.begin():
        assert (await admin_store.execute(select(finding.c.status))).scalar_one() == "exception"
        await admin_store.execute(
            update(url_check).values(next_check_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    job = await claim(admin_store, key, owner)
    await finish(admin_store, settings, job, owner, Observation("reachable", 200))
    assert await claim(admin_store, key, owner) is None
    async with admin_store.begin():
        stored = (await admin_store.execute(select(finding))).mappings().one()
        assert stored["status"] == "resolved"
        assert (
            stored["reviewed_subject"] == "admin:test" and stored["exception_reason"] == "Approved"
        )
        assert (
            await admin_store.execute(select(url_check.c.last_success_at))
        ).scalar_one() is not None


async def test_url_crash_reclaim_changed_source_and_credentials(admin_store):
    owner = uuid4()
    rows = [dict(kind="venue", key=str(uid(20)), field="web_link", url="http://public.test")]
    key = (await discover(admin_store, rows))[0]
    assert await claim(admin_store, key, owner)
    async with admin_store.begin():
        await admin_store.execute(
            update(url_check).values(lease_until=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert await claim(admin_store, key, uuid4())
    rows[0]["url"] = "https://new.test"
    assert await discover(admin_store, rows) == [key]
    job = await claim(admin_store, key, owner)
    assert job["url"] == "https://new.test" and job["failure_count"] == 0
    rows[0]["url"] = "https://operator:secret@private.test"
    assert await discover(admin_store, rows) == []


async def test_url_worker_once_reads_source_and_bounds_requests(
    admin_store, db_connection, database, settings, monkeypatch
):
    from pydantic import SecretStr

    # Committed source setup is removed explicitly; ordinary source engine is read-only.
    from sqlalchemy.ext.asyncio import create_async_engine

    from app import url_check_worker
    from app.admin_database import create_admin_engine
    from app.database import create_engine

    setup = create_async_engine(database[0])
    async with setup.begin() as connection:
        await connection.execute(
            text("UPDATE uranus.venue SET web_link='https://public.test/' WHERE uuid=:id"),
            {"id": uid(20)},
        )
    settings.database_url = SecretStr(database[0])
    settings.url_check_batch_size = 1
    source, admin = create_engine(settings), create_admin_engine(settings)
    calls = []

    async def observe(url):
        calls.append(url)
        return Observation("reachable", 200)

    monkeypatch.setattr(url_check_worker, "check_url", observe)
    try:
        assert await url_check_worker.work_once(source, admin, settings) == 1
        assert len(calls) == 1
        assert await url_check_worker.work_once(source, admin, settings) == 0
    finally:
        await source.dispose()
        await admin.dispose()
        async with setup.begin() as connection:
            await connection.execute(
                text("UPDATE uranus.venue SET web_link=NULL WHERE uuid=:id"), {"id": uid(20)}
            )
        await setup.dispose()


async def test_url_success_does_not_resolve_another_field(admin_store, settings):
    from app.services.checks import persist_results
    from app.services.quality.core import RuleResult, make_finding

    now = datetime.now(UTC)
    items = [
        make_finding("url_unreachable", "venue", str(uid(20)), field, "Unreachable", now)
        for field in ("web_link", "ticket_link")
    ]
    async with admin_store.begin():
        await persist_results(admin_store, [RuleResult("url_unreachable", items, set())], now)
    key = (
        await discover(
            admin_store,
            [dict(kind="venue", key=str(uid(20)), field="web_link", url="https://public.test")],
        )
    )[0]
    owner = uuid4()
    job = await claim(admin_store, key, owner)
    await finish(admin_store, settings, job, owner, Observation("reachable", 200))
    async with admin_store.begin():
        states = dict(
            (await admin_store.execute(select(finding.c.field, finding.c.status))).tuples().all()
        )
    assert states == {"web_link": "resolved", "ticket_link": "open"}


async def test_parallel_url_claim_only_one_owner(admin_store, settings):
    import asyncio

    from app.admin_database import create_admin_engine

    key = (
        await discover(
            admin_store,
            [dict(kind="venue", key=str(uid(20)), field="web_link", url="https://public.test")],
        )
    )[0]
    engine = create_admin_engine(settings)

    async def attempt():
        async with engine.connect() as connection:
            return await claim(connection, key, uuid4())

    try:
        results = await asyncio.gather(attempt(), attempt())
        assert sum(result is not None for result in results) == 1
    finally:
        await engine.dispose()
