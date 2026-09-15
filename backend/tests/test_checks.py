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


async def test_check_and_review_api(admin_store, db_client, headers):
    response = await db_client.post("/api/v1/check-runs", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "success"
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
    from app.services.checks import LOCK_KEY

    await admin_store.execute(text("SELECT pg_advisory_lock(:key)"), {"key": LOCK_KEY})
    await admin_store.commit()
    try:
        with pytest.raises(APIError) as error:
            await run_check(db_connection, db_connection, settings)
        assert error.value.code == "check_run_conflict"
    finally:
        await admin_store.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY})
        await admin_store.commit()


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
