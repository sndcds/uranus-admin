from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.admin_database import assert_admin_boundary
from app.admin_tables import finding
from app.errors import APIError
from app.schemas.checks import ReviewUpdate
from app.schemas.finding import FindingFilters
from app.services.checks import persist_results, persisted_page, review, run_check
from app.services.quality.core import RuleResult, make_finding
from tests.conftest import uid


@pytest.mark.parametrize(
    "rule,kind,key,prepare,repair",
    [
        (
            "venue_missing_geolocation",
            "venue",
            str(uid(20)),
            None,
            "UPDATE uranus.venue SET point=ST_GeomFromText('POINT(9 54)',4326)",
        ),
        (
            "partner_long_pending",
            "partner_request",
            f"partner-request:{uid(10)}:{uid(11)}",
            "UPDATE uranus.organization_partner_request SET created_at=:old",
            "UPDATE uranus.organization_partner_request SET status='accepted'",
        ),
        (
            "team_invitation_old",
            "team_membership",
            f"membership:{uid(10)}:{uid(1)}",
            "UPDATE uranus.organization_member_link SET invited_at=:old",
            "UPDATE uranus.organization_member_link SET has_joined=true",
        ),
    ],
)
async def test_persistence_lifecycle_for_source_keys(
    admin_store, db_connection, settings, now, rule, kind, key, prepare, repair
):
    from app.services.quality.engine import scan

    if prepare:
        await db_connection.execute(
            text(prepare), {"old": (now - timedelta(days=60)).replace(tzinfo=None)}
        )
    original = next(
        f
        for r in await scan(db_connection, settings, now)
        for f in r.findings
        if f.rule == rule and f.entity_key == key
    )
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    filters = FindingFilters(rule=rule)
    item = next(
        f for f in (await persisted_page(admin_store, filters, now)).items if f.entity_key == key
    )
    excluded = {"first_seen_at", "last_seen_at", "entity_id"}
    assert item.model_dump(exclude=excluded) == original.model_dump(exclude=excluded)
    assert item.entity_type == kind
    await review(
        admin_store,
        db_connection,
        ReviewUpdate(
            finding_id=item.id,
            status="exception",
            exception_reason="Checked",
            comment="Keep",
            assigned_to=uid(1),
        ),
        "reviewer",
        now,
    )
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    stored = next(
        f for f in (await persisted_page(admin_store, filters, now)).items if f.id == item.id
    )
    assert stored.status == "exception" and stored.exception_reason == "Checked"
    assert stored.reviewed_subject == "reviewer" and stored.assigned_to == uid(1)
    assert stored.comment == "Keep" and stored.reviewed_at == now
    await db_connection.execute(text(repair))
    assert (await run_check(db_connection, admin_store, settings)).status == "success"
    resolved = next(
        f for f in (await persisted_page(admin_store, filters, now)).items if f.id == item.id
    )
    assert resolved.status == "resolved" and resolved.resolved_at
    assert resolved.first_seen_at == item.first_seen_at


@pytest.mark.parametrize("key", [str(uid(20)), f"membership:{uid(10)}:{uid(1)}"])
async def test_foundation_row_reload_without_optional_metadata(admin_store, now, key):
    async with admin_store.begin():
        await admin_store.execute(
            finding.insert().values(
                id="legacy",
                rule="legacy_rule",
                severity="warning",
                entity_type="legacy",
                entity_key=key,
                message="Legacy",
                first_seen_at=now,
                last_seen_at=now,
            )
        )
    item = (await persisted_page(admin_store, FindingFilters(), now)).items[0]
    assert item.entity_key == item.entity_name == key
    assert item.action is None and item.organization_id is None and item.metadata == {}
    assert item.priority_score > 0 and item.priority_reasons
    assert item.status == "open" and item.snoozed_until is None


async def test_runs_are_idempotent_and_resolve_only_covered_objects(
    admin_store, db_connection, settings, now
):
    one = await run_check(db_connection, admin_store, settings)
    assert one.status == "success" and one.finding_count == 2 and one.rule_count == 19
    two = await run_check(db_connection, admin_store, settings)
    page = await persisted_page(admin_store, FindingFilters(), now)
    assert page.pagination.total == 2 and page.items[0].first_seen_at <= page.items[0].last_seen_at
    first_seen = {f.id: f.first_seen_at for f in page.items}
    await db_connection.execute(
        text("UPDATE uranus.venue SET point=ST_GeomFromText('POINT(9 54)',4326) WHERE uuid=:id"),
        {"id": uid(20)},
    )
    three = await run_check(db_connection, admin_store, settings)
    assert three.status == "success" and three.finding_count == 1
    page = await persisted_page(admin_store, FindingFilters(status="resolved"), now)
    assert page.pagination.total == 1 and page.items[0].entity_key == str(uid(20))
    assert page.items[0].first_seen_at == first_seen[page.items[0].id]
    await db_connection.execute(
        text("UPDATE uranus.venue SET point=NULL WHERE uuid=:id"), {"id": uid(20)}
    )
    await run_check(db_connection, admin_store, settings)
    page = await persisted_page(admin_store, FindingFilters(), now)
    assert all(f.status == "open" and f.resolved_at is None for f in page.items)
    assert all(f.first_seen_at == first_seen[f.id] for f in page.items)
    assert one.id != two.id


async def test_failed_and_partial_scans_never_close(
    admin_store, db_connection, settings, now, monkeypatch
):
    await run_check(db_connection, admin_store, settings)

    async def broken(*args):
        raise RuntimeError("secret SQL token")

    monkeypatch.setattr("app.services.checks.scan", broken)
    failed = await run_check(db_connection, admin_store, settings)
    assert failed.status == "failed" and "secret" not in failed.error_message
    async with admin_store.begin():
        await persist_results(
            admin_store,
            [
                RuleResult("venue_missing_geolocation", covered={("venue", str(uid(20)))}),
                RuleResult("url_syntax", success=False),
            ],
            now,
        )
    page = await persisted_page(admin_store, FindingFilters(), now)
    assert all(f.status == "open" for f in page.items)
    async with admin_store.begin():
        await persist_results(
            admin_store,
            [RuleResult("venue_missing_geolocation", covered={("venue", str(uid(999)))})],
            now,
        )
    assert not (await persisted_page(admin_store, FindingFilters(status="resolved"), now)).items


async def test_review_exception_snooze_assignment_and_recheck(
    admin_store, db_connection, settings, now
):
    await run_check(db_connection, admin_store, settings)
    item = (await persisted_page(admin_store, FindingFilters(), now)).items[0]
    reviewed = await review(
        admin_store,
        db_connection,
        ReviewUpdate(
            finding_id=item.id,
            status="exception",
            exception_reason="Agreed",
            assigned_to=uid(1),
            comment="Review",
        ),
        "development-only",
        now,
    )
    assert reviewed.reviewed_by is None and reviewed.reviewed_subject == "development-only"
    assert reviewed.assigned_to == uid(1) and reviewed.status == "exception"
    await run_check(db_connection, admin_store, settings)
    assert (await persisted_page(admin_store, FindingFilters(status="exception"), now)).items
    snoozed = await review(
        admin_store,
        db_connection,
        ReviewUpdate(finding_id=item.id, status="snoozed", snoozed_until=now + timedelta(days=2)),
        "development-only",
        now,
    )
    assert snoozed.assigned_to == uid(1) and snoozed.exception_reason is None
    with pytest.raises(APIError):
        await review(
            admin_store,
            db_connection,
            ReviewUpdate(finding_id=item.id, status="in_progress", assigned_to=uid(999)),
            "development-only",
            now,
        )
    with pytest.raises(ValidationError):
        ReviewUpdate(finding_id=item.id, status="resolved")
    with pytest.raises(ValidationError):
        ReviewUpdate(finding_id=item.id, status="exception")
    with pytest.raises(APIError):
        await review(
            admin_store,
            db_connection,
            ReviewUpdate(
                finding_id=item.id, status="snoozed", snoozed_until=now - timedelta(seconds=1)
            ),
            "development-only",
            now,
        )


async def test_restricted_storage_cannot_write_domain(admin_store, db_connection):
    await assert_admin_boundary(admin_store)
    await admin_store.rollback()
    with pytest.raises(DBAPIError):
        await admin_store.execute(text("UPDATE uranus.venue SET name='forbidden'"))
    await admin_store.rollback()
    with pytest.raises(APIError):
        await assert_admin_boundary(
            db_connection
        )  # Source fixture role is deliberately a superuser.


async def test_changed_exception_and_expired_snooze_reopen(admin_store, now):
    item = make_finding(
        "url_syntax",
        "license",
        "CC:license",
        "url",
        "Invalid URL",
        now,
        metadata={"reason": "missing_scheme"},
    )
    result = RuleResult(item.rule, [item], {(item.entity_type, item.entity_key)})
    async with admin_store.begin():
        await persist_results(admin_store, [result], now)
        await admin_store.execute(
            finding.update().values(status="exception", exception_reason="Accepted")
        )
    async with admin_store.begin():
        await persist_results(admin_store, [result], now + timedelta(minutes=1))
    assert (await persisted_page(admin_store, FindingFilters(status="exception"), now)).items
    item.metadata = {"reason": "missing_host"}
    async with admin_store.begin():
        await persist_results(admin_store, [result], now + timedelta(minutes=2))
    assert (await persisted_page(admin_store, FindingFilters(status="open"), now)).items
    async with admin_store.begin():
        await admin_store.execute(finding.update().values(status="snoozed", snoozed_until=now))
        await persist_results(admin_store, [result], now + timedelta(minutes=3))
    assert (await persisted_page(admin_store, FindingFilters(status="open"), now)).items


async def test_check_and_review_api(admin_store, db_client, headers, db_connection, settings):
    response = await db_client.post("/api/v1/check-runs", headers=headers)
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "queued"
    identifier = response.json()["id"]
    from app.services.checks import claim_check, execute_check

    job = await claim_check(admin_store, settings)
    assert job is not None
    assert (await execute_check(db_connection, admin_store, settings, *job)).status == "success"
    response = await db_client.get(f"/api/v1/check-runs/{identifier}", headers=headers)
    assert response.status_code == 200 and response.json()["status"] == "success"
    response = await db_client.get("/api/v1/findings?mode=persisted", headers=headers)
    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert response.json()["mode"] == "persisted" and item["first_seen_at"]
    response = await db_client.patch(
        "/api/v1/finding-reviews",
        headers=headers,
        json={"finding_id": item["id"], "status": "in_progress"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["reviewed_subject"] == "development-only"
    response = await db_client.get("/api/v1/check-runs", headers=headers)
    assert response.status_code == 200 and response.json()["pagination"]["total"] == 1


async def test_concurrent_run_lock(admin_store, db_connection, settings):
    from app.services.checks import enqueue_check

    await enqueue_check(admin_store)
    with pytest.raises(APIError) as error:
        await run_check(db_connection, admin_store, settings)
    assert error.value.code == "check_run_conflict"


async def test_persisted_history_survives_source_outage(admin_store, db_client, headers):
    from app.database import get_connection

    app = db_client._transport.app

    async def unavailable(request):
        raise OSError("Source unavailable")
        yield

    app.dependency_overrides[get_connection] = unavailable
    response = await db_client.get("/api/v1/findings?mode=persisted", headers=headers)
    assert response.status_code == 200 and response.json()["items"] == []


def test_review_rejects_unrecognized_fields():
    with pytest.raises(ValidationError):
        ReviewUpdate(finding_id="f", status="open", resolved_at="2026-09-14T12:00:00Z")


async def test_queue_exception_reopens_when_requesting_user_changes(
    admin_store, db_connection, settings, now
):
    await db_connection.execute(
        text("UPDATE uranus.organization_partner_request SET created_at=:old"),
        {"old": (now - timedelta(days=60)).replace(tzinfo=None)},
    )
    await run_check(db_connection, admin_store, settings)
    item = (
        await persisted_page(admin_store, FindingFilters(rule="partner_long_pending"), now)
    ).items[0]
    await review(
        admin_store,
        db_connection,
        ReviewUpdate(finding_id=item.id, status="exception", exception_reason="Reviewed requester"),
        "development-only",
        now,
    )
    await run_check(db_connection, admin_store, settings)
    assert (
        await persisted_page(admin_store, FindingFilters(rule=item.rule, status="exception"), now)
    ).items
    await db_connection.execute(
        text("UPDATE uranus.organization_partner_request SET from_user_uuid=:id"), {"id": uid(999)}
    )
    await run_check(db_connection, admin_store, settings)
    assert (
        await persisted_page(admin_store, FindingFilters(rule=item.rule, status="open"), now)
    ).items


async def test_default_reads_never_scan(admin_store, db_client, headers, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("Normal GET must not scan Uranus")

    monkeypatch.setattr("app.services.dashboard.scan", forbidden)
    monkeypatch.setattr("app.services.quality.engine.scan", forbidden)
    for path in ("/api/v1/findings", "/api/v1/dashboard/summary"):
        response = await db_client.get(path, headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["quality"] if "quality" in body else body)["mode"] == "persisted"


async def test_default_findings_requires_storage_without_live_fallback(client, headers):
    response = await client.get("/api/v1/findings", headers=headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "admin_storage_unconfigured"


async def test_review_aging_snooze_and_incomplete_runs(admin_store, db_connection, now):
    item = make_finding(
        "age_rule",
        "user",
        str(uid(1)),
        "status",
        "Old",
        now,
        metadata={"age_days": 30, "source_fingerprint": "stable"},
    )
    result = RuleResult(item.rule, [item], {("user", item.entity_key)})
    async with admin_store.begin():
        await persist_results(admin_store, [result], now)
    await review(
        admin_store,
        db_connection,
        ReviewUpdate(finding_id=item.id, status="exception", exception_reason="Known"),
        "a",
        now,
    )
    item.metadata["age_days"] = 31
    async with admin_store.begin():
        await persist_results(admin_store, [result], now + timedelta(days=1))
    assert (await persisted_page(admin_store, FindingFilters(), now)).items[0].status == "exception"
    await review(
        admin_store,
        db_connection,
        ReviewUpdate(finding_id=item.id, status="snoozed", snoozed_until=now + timedelta(days=3)),
        "a",
        now,
    )
    async with admin_store.begin():
        await persist_results(admin_store, [result], now + timedelta(days=2))
    assert (await persisted_page(admin_store, FindingFilters(), now)).items[0].status == "snoozed"
    async with admin_store.begin():
        await persist_results(admin_store, [result], now + timedelta(days=3))
    assert (await persisted_page(admin_store, FindingFilters(), now)).items[0].status == "open"


@pytest.mark.parametrize("fail", [False, True])
async def test_parallel_checks_and_reviews_release_lock(
    admin_store, db_connection, settings, now, monkeypatch, fail
):
    import asyncio

    from app.admin_database import create_admin_engine
    from app.services.quality.engine import scan

    real_results = await scan(db_connection, settings, now)
    async with admin_store.begin():
        await persist_results(admin_store, real_results, now)
    item = (await persisted_page(admin_store, FindingFilters(), now)).items[0]
    entered, proceed = asyncio.Event(), asyncio.Event()

    async def paused(*args):
        entered.set()
        await proceed.wait()
        if fail:
            raise RuntimeError("scan failed")
        return real_results

    monkeypatch.setattr("app.services.checks.scan", paused)
    task = asyncio.create_task(run_check(db_connection, admin_store, settings))
    engine = create_admin_engine(settings)
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        async with engine.connect() as peer:
            with pytest.raises(APIError) as error:
                await run_check(db_connection, peer, settings)
            assert error.value.code == "check_run_conflict"
            during = await review(
                peer,
                db_connection,
                ReviewUpdate(
                    finding_id=item.id,
                    status="in_progress",
                    comment="During scan",
                    assigned_to=uid(1),
                ),
                "peer",
                now,
            )
            assert during.status == "in_progress"
            proceed.set()
            run = await asyncio.wait_for(task, timeout=5)
            assert run.status == ("failed" if fail else "success")
            preserved = (await persisted_page(peer, FindingFilters(), now)).items
            reviewed = next(f for f in preserved if f.id == item.id)
            assert reviewed.status == "in_progress" and reviewed.comment == "During scan"
            assert reviewed.assigned_to == uid(1) and reviewed.reviewed_subject == "peer"
            # A different physical connection can immediately acquire the released lock.
            updated = await review(
                peer,
                db_connection,
                ReviewUpdate(finding_id=item.id, status="in_progress"),
                "peer",
                now,
            )
            assert updated.status == "in_progress"
            with pytest.raises(APIError) as error:
                await review(
                    peer,
                    db_connection,
                    ReviewUpdate(finding_id="missing", status="open"),
                    "peer",
                    now,
                )
            assert error.value.code == "finding_not_found"
        # The failing review also released its lock.
        assert (
            await review(
                admin_store,
                db_connection,
                ReviewUpdate(finding_id=item.id, status="open"),
                "a",
                now,
            )
        ).status == "open"
    finally:
        proceed.set()
        await task
        await engine.dispose()


async def test_partial_or_empty_run_is_failed(
    admin_store, db_connection, settings, now, monkeypatch
):
    await run_check(db_connection, admin_store, settings)
    for results in (
        [],
        [RuleResult("venue_missing_geolocation", covered={("venue", str(uid(20)))})],
        [
            RuleResult("venue_missing_geolocation", covered={("venue", str(uid(20)))}),
            RuleResult("url_syntax", success=False),
        ],
    ):

        async def partial(*args, results=results):
            return results

        monkeypatch.setattr("app.services.checks.scan", partial)
        assert (await run_check(db_connection, admin_store, settings)).status == "failed"
        assert not (await persisted_page(admin_store, FindingFilters(status="resolved"), now)).items


async def test_persisted_sql_filters_counts_and_priority_match_reload(admin_store, now):
    from app.schemas.finding import Severity
    from app.services.checks import persisted_counts
    from app.services.quality.engine import findings_page

    items = [
        make_finding(
            "example_rule",
            "license",
            f"license:{i}",
            "url",
            "Broken",
            now,
            severity=list(Severity)[i % 3],
            published=i % 2 == 0,
            soon=i % 2 == 0,
            organization={"uuid": uid(10 if i % 2 else 11), "name": "Org"},
        )
        for i in range(20)
    ]
    async with admin_store.begin():
        await persist_results(admin_store, [RuleResult("example_rule", items)], now)
        await admin_store.execute(
            finding.update()
            .where(finding.c.id == items[0].id)
            .values(status="resolved", resolved_at=now)
        )
    all_items = (await persisted_page(admin_store, FindingFilters(), now)).items
    for extra in (
        {},
        {"severity": "warning"},
        {"organization_id": uid(10)},
        {"status": "resolved"},
        {"entity_type": "license"},
        {"rule": "missing"},
    ):
        for page in (1, 2, 100):
            filters = FindingFilters(page=page, page_size=3, **extra)
            expected = findings_page(all_items, filters, now)
            actual = await persisted_page(admin_store, filters, now)
            assert actual.items == expected.items and actual.pagination == expected.pagination
    counts, urgent = await persisted_counts(admin_store)
    active = [item for item in all_items if item.status != "resolved"]
    assert counts.total == len(active) == 19
    assert counts.errors == sum(item.severity == "error" for item in active)
    assert counts.warnings == sum(item.severity == "warning" for item in active)
    assert counts.info == sum(item.severity == "info" for item in active)
    assert urgent == sum(
        item.priority <= 2 or "published_soon" in item.priority_reasons for item in active
    )


async def test_cancelled_scan_releases_session_lock(admin_store, db_connection, settings):
    import asyncio
    from unittest.mock import patch

    from app.admin_database import create_admin_engine
    from app.services.checks import lock, unlock

    entered = asyncio.Event()

    async def blocked(*args):
        entered.set()
        await asyncio.Event().wait()

    engine = create_admin_engine(settings)
    try:
        with patch("app.services.checks.scan", blocked):
            task = asyncio.create_task(run_check(db_connection, admin_store, settings))
            try:
                await asyncio.wait_for(entered.wait(), 5)
            finally:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
        async with engine.connect() as peer:
            await lock(peer)
            await unlock(peer)
    finally:
        await engine.dispose()


async def test_claim_lease_recovery_and_fencing(admin_store, db_connection, settings, now):
    from app.admin_tables import check_run
    from app.services.checks import claim_check, enqueue_check, execute_check, renew_lease

    queued = await enqueue_check(admin_store)
    job = await claim_check(admin_store, settings)
    assert job and str(job[0]) == str(queued.id)
    assert await claim_check(admin_store, settings) is None
    assert await renew_lease(admin_store, settings, *job)
    async with admin_store.begin():
        await admin_store.execute(check_run.update().values(lease_until=now - timedelta(seconds=1)))
    assert not await renew_lease(admin_store, settings, *job)
    assert await claim_check(admin_store, settings) is None
    # A stale process cannot commit, even if its scan eventually completes successfully.
    result = await execute_check(db_connection, admin_store, settings, *job)
    assert result.status == "failed" and result.finding_count == 0
    assert not (await persisted_page(admin_store, FindingFilters(), now)).items
    assert (await run_check(db_connection, admin_store, settings)).status == "success"


async def test_worker_processes_durable_job_once(admin_store, database, settings, monkeypatch):
    import asyncio

    from pydantic import SecretStr

    from app.admin_database import create_admin_engine
    from app.check_worker import work_once
    from app.database import create_engine
    from app.services.checks import enqueue_check
    from app.services.quality.engine import scan as real_scan

    settings.database_url = SecretStr(database[0])
    source, admin = create_engine(settings), create_admin_engine(settings)
    await enqueue_check(admin_store)
    entered, proceed = asyncio.Event(), asyncio.Event()

    async def paused(*args):
        entered.set()
        await proceed.wait()
        return await real_scan(*args)

    monkeypatch.setattr("app.services.checks.scan", paused)
    task = asyncio.create_task(work_once(source, admin, settings))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert not await work_once(source, admin, settings)
        proceed.set()
        assert await asyncio.wait_for(task, 10)
        from sqlalchemy import select

        from app.admin_tables import check_run

        async with admin_store.begin():
            assert (await admin_store.execute(select(check_run.c.status))).scalar_one() == "success"
    finally:
        proceed.set()
        await task
        await source.dispose()
        await admin.dispose()


async def test_enqueue_never_reads_source_or_scans(admin_store, db_client, headers, monkeypatch):
    from app.database import get_connection

    async def forbidden(*args):
        raise AssertionError("HTTP must only enqueue")

    db_client._transport.app.dependency_overrides[get_connection] = forbidden
    monkeypatch.setattr("app.services.checks.scan", forbidden)
    response = await db_client.post("/api/v1/check-runs", headers=headers)
    assert response.status_code == 202 and response.json()["status"] == "queued"
    assert (await db_client.post("/api/v1/check-runs", headers=headers)).status_code == 409
    assert (
        await db_client.get(f"/api/v1/check-runs/{uid(999)}", headers=headers)
    ).status_code == 404


async def test_worker_cancellation_marks_job_failed(admin_store, database, settings, monkeypatch):
    import asyncio

    from pydantic import SecretStr
    from sqlalchemy import select

    from app.admin_database import create_admin_engine
    from app.admin_tables import check_run
    from app.check_worker import work_once
    from app.database import create_engine
    from app.services.checks import enqueue_check

    settings.database_url = SecretStr(database[0])
    source, admin = create_engine(settings), create_admin_engine(settings)
    await enqueue_check(admin_store)
    entered = asyncio.Event()

    async def interrupted(*args):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("app.services.checks.scan", interrupted)
    task = asyncio.create_task(work_once(source, admin, settings))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        async with admin_store.begin():
            assert (await admin_store.execute(select(check_run.c.status))).scalar_one() == "failed"
            assert (await admin_store.execute(select(finding.c.id))).first() is None
    finally:
        await source.dispose()
        await admin.dispose()


async def test_heartbeat_does_not_block_final_persistence(admin_store, settings):
    import asyncio
    from uuid import uuid4

    from sqlalchemy import select

    from app.admin_database import create_admin_engine
    from app.admin_tables import check_run
    from app.services.checks import claim_check, enqueue_check, renew_lease

    await enqueue_check(admin_store)
    job = await claim_check(admin_store, settings)
    assert job
    engine = create_admin_engine(settings)
    try:
        async with engine.connect() as peer:
            async with admin_store.begin():
                # execute_check holds this lock while saving all findings atomically.
                await admin_store.execute(
                    select(check_run.c.id).where(check_run.c.id == job[0]).with_for_update()
                )
                assert await asyncio.wait_for(renew_lease(peer, settings, *job), 1)
                assert not await asyncio.wait_for(renew_lease(peer, settings, job[0], uuid4()), 1)
            assert await renew_lease(peer, settings, *job)
    finally:
        await engine.dispose()
