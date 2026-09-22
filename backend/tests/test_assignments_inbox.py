from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import ValidationError
from sqlalchemy import insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.admin_tables import (
    assignment_event,
    auth_account,
    auth_system_admin,
    finding,
    geocode_request,
    notification_delivery,
)
from app.errors import APIError
from app.schemas.assignments import (
    AssignmentCreate,
    AssignmentLookup,
    AssignmentUpdate,
    InboxFilters,
)
from app.services.assignments import create_assignment, update_assignment
from app.services.inbox import inbox_page, map_item
from tests.conftest import uid

NOW = datetime(2026, 10, 25, 10, tzinfo=UTC)  # Europe/Berlin DST transition day.


async def provision_admin(database, identifier, login="operator", *, active=True, granted=True):
    engine = create_async_engine(database[0], poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.execute(
            insert(auth_account).values(
                id=identifier,
                login=login,
                password_hash="not-returned-test-hash",
                is_active=active,
            )
        )
        if granted:
            await connection.execute(
                insert(auth_system_admin).values(account_id=identifier, granted_by="test-operator")
            )
    await engine.dispose()


async def add_finding(admin_store, identity="finding:one", severity="error", field="description"):
    await admin_store.execute(
        finding.insert().values(
            id=identity,
            rule="missing_description",
            severity=severity,
            entity_type="event",
            entity_key=str(uid(30)),
            field=field,
            message="Beschreibung fehlt",
            first_seen_at=NOW - timedelta(days=2),
            last_seen_at=NOW - timedelta(hours=1),
            metadata={"finding": {"entity_name": "Event 30", "priority_score": 200}},
            status="open",
        )
    )
    await admin_store.commit()


def creation(admin_id, **extra):
    return AssignmentCreate(
        finding_id="finding:one",
        assigned_to_admin_id=admin_id,
        **extra,
    )


def test_assignment_contract_rejects_ambiguous_and_forged_state():
    with pytest.raises(ValidationError):
        AssignmentCreate(assigned_to_admin_id=uid(800))
    with pytest.raises(ValidationError):
        AssignmentCreate(
            finding_id="finding:one",
            workflow_type="geocode_request",
            workflow_key=str(uid(1)),
            assigned_to_admin_id=uid(800),
        )
    with pytest.raises(ValidationError):
        AssignmentCreate(
            workflow_type="geocode_request",
            workflow_key=str(uid(1)),
            assigned_to_admin_id=uid(800),
        )
    with pytest.raises(ValidationError):
        AssignmentUpdate(
            version=1,
            assigned_to_admin_id=uid(800),
            status="invented",
        )
    assert AssignmentLookup(finding_id="finding:one").finding_id == "finding:one"
    with pytest.raises(ValidationError):
        AssignmentLookup(workflow_type="geocode_request")


@pytest.mark.parametrize(
    "entity_type,entity_key", [("event_date", str(uid(40))), ("membership", "a/b:c&d")]
)
def test_unassigned_finding_links_to_its_rule_and_entity_without_source_presentation(
    entity_type, entity_key
):
    # Unassigned rows have no assignment finding_id in the inbox UNION projection.
    item = map_item(
        {
            "id": f"finding:date_rule:{entity_type}:{entity_key}:end_date",
            "kind": "finding",
            "title": "Qualitätsprüfung",
            "summary": "Das Enddatum liegt vor dem Startdatum.",
            "entity_type": entity_type,
            "entity_key": entity_key,
            "fallback_entity_name": "Testtermin",
            "severity": "error",
            "status": "open",
            "occurred_at": NOW,
            "due_at": None,
            "assignment_id": None,
            "finding_id": None,
            "rule": "event_date_end_before_start",
        },
        None,
        NOW,
        NOW.replace(hour=0),
        NOW.replace(hour=0) + timedelta(days=1),
    )
    assert item.assignment is None and item.entity_action is None
    assert item.entity_name == "Testtermin"
    url = urlsplit(item.href)
    assert url.path == "/findings"
    assert parse_qs(url.query) == {
        "entity_key": [entity_key],
        "rule": ["event_date_end_before_start"],
    }


async def test_assignment_lifecycle_conflict_and_append_only_history(database, admin_store):
    await provision_admin(database, uid(800))
    await add_finding(admin_store)
    created = await create_assignment(
        admin_store,
        creation(uid(800), status="in_progress", due_at=NOW + timedelta(days=1)),
        "admin:test",
    )
    assert created.assigned_to.login == "operator"
    assert created.entity_key == str(uid(30)) and created.version == 1
    with pytest.raises(APIError) as duplicate:
        await create_assignment(admin_store, creation(uid(800)), "admin:test")
    assert duplicate.value.code == "assignment_conflict"

    completed = await update_assignment(
        admin_store,
        created.id,
        AssignmentUpdate(
            version=1,
            assigned_to_admin_id=uid(800),
            status="done",
            due_at=created.due_at,
        ),
        "admin:test",
    )
    assert completed.status == "done" and completed.completed_at and completed.version == 2
    with pytest.raises(APIError) as stale:
        await update_assignment(
            admin_store,
            created.id,
            AssignmentUpdate(
                version=1,
                assigned_to_admin_id=uid(800),
                status="open",
            ),
            "admin:test",
        )
    assert stale.value.code == "assignment_conflict"
    rows = (
        (
            await admin_store.execute(
                select(assignment_event).where(assignment_event.c.assignment_id == created.id)
            )
        )
        .mappings()
        .all()
    )
    assert [(row["version"], row["kind"]) for row in rows] == [
        (1, "created"),
        (2, "completed"),
    ]
    with pytest.raises(DBAPIError):
        await admin_store.execute(text("UPDATE admin.assignment_event SET actor='forged'"))
    await admin_store.rollback()


async def test_assignment_requires_active_system_admin(database, admin_store):
    await add_finding(admin_store)
    for identifier, active, granted in [
        (uid(801), False, True),
        (uid(802), True, False),
    ]:
        await provision_admin(
            database,
            identifier,
            f"operator-{identifier.int}",
            active=active,
            granted=granted,
        )
        with pytest.raises(APIError) as error:
            await create_assignment(admin_store, creation(identifier), "admin:test")
        assert error.value.code == "assignment_assignee_invalid"


async def test_workflow_assignment_derives_and_verifies_durable_entity_identity(
    database, admin_store
):
    await provision_admin(database, uid(800))
    await admin_store.execute(
        geocode_request.insert().values(
            id=uid(850),
            entity_type="venue",
            entity_key=uid(20),
            source_fingerprint="a" * 64,
            query_fingerprint="b" * 64,
            status="failed",
            generation=1,
            query_version=1,
            scoring_version=1,
            attempt_count=1,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    await admin_store.commit()
    body = AssignmentCreate(
        workflow_type="geocode_request",
        workflow_key=str(uid(850)),
        entity_type="venue",
        entity_key=str(uid(20)),
        assigned_to_admin_id=uid(800),
    )
    created = await create_assignment(admin_store, body, "admin:test")
    assert created.entity_type == "venue"
    assert created.entity_key == str(uid(20))
    assert created.workflow_key == str(uid(850))

    mismatched = body.model_copy(update={"workflow_key": str(uid(851))})
    await admin_store.execute(
        geocode_request.insert().values(
            id=uid(851),
            entity_type="venue",
            entity_key=uid(21),
            source_fingerprint="c" * 64,
            query_fingerprint="d" * 64,
            status="failed",
            generation=1,
            query_version=1,
            scoring_version=1,
            attempt_count=1,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    await admin_store.commit()
    with pytest.raises(APIError) as mismatch:
        await create_assignment(admin_store, mismatched, "admin:test")
    assert mismatch.value.code == "assignment_task_invalid"


async def test_inbox_deduplicates_assignment_and_filters_mine(database, admin_store, db_connection):
    await provision_admin(database, uid(800))
    await add_finding(admin_store)
    before_assignment = await inbox_page(
        admin_store, db_connection, InboxFilters(), NOW, "Europe/Berlin", f"admin:{uid(800)}"
    )
    unassigned_finding = next(item for item in before_assignment.items if item.kind == "finding")
    assert unassigned_finding.href == (f"/findings?entity_key={uid(30)}&rule=missing_description")
    assigned = await create_assignment(
        admin_store,
        creation(uid(800), due_at=NOW - timedelta(minutes=1)),
        f"admin:{uid(800)}",
    )
    page = await inbox_page(
        admin_store, db_connection, InboxFilters(), NOW, "Europe/Berlin", f"admin:{uid(800)}"
    )
    matching = [item for item in page.items if item.entity_key == str(uid(30))]
    assert len(matching) == 1
    assert matching[0].kind == "assignment" and matching[0].assignment.id == assigned.id
    assert matching[0].href == unassigned_finding.href
    assert page.counts.mine == 1 and page.counts.overdue == 1
    mine = await inbox_page(
        admin_store,
        db_connection,
        InboxFilters(scope="mine"),
        NOW,
        "Europe/Berlin",
        f"admin:{uid(800)}",
    )
    assert [item.id for item in mine.items] == [f"assignment:{assigned.id}"]
    unassigned = await inbox_page(
        admin_store,
        db_connection,
        InboxFilters(scope="unassigned"),
        NOW,
        "Europe/Berlin",
        f"admin:{uid(800)}",
    )
    assert not [item for item in unassigned.items if item.entity_key == str(uid(30))]


async def test_inbox_aggregates_safe_workflow_tasks_without_secret_values(
    admin_store, db_connection
):
    await admin_store.execute(
        geocode_request.insert().values(
            id=uid(850),
            entity_type="venue",
            entity_key=uid(20),
            source_fingerprint="a" * 64,
            query_fingerprint="b" * 64,
            status="failed",
            generation=1,
            query_version=1,
            scoring_version=1,
            attempt_count=1,
            last_error="provider_unavailable",
            created_at=NOW - timedelta(hours=2),
            updated_at=NOW - timedelta(hours=1),
        )
    )
    await admin_store.execute(
        notification_delivery.insert().values(
            id=uid(851),
            organization_id=uid(10),
            recipient="secret@example.invalid",
            locale="de",
            channel="email",
            delivery_kind="initial",
            status="permanent_failure",
            subject="Private subject",
            message_fingerprint="c" * 64,
            snapshot={"private": "not returned"},
            attempt_count=5,
            last_error="private provider response",
            created_at=NOW - timedelta(hours=3),
            updated_at=NOW - timedelta(hours=1),
        )
    )
    await admin_store.commit()
    page = await inbox_page(
        admin_store,
        db_connection,
        InboxFilters(),
        NOW,
        "Europe/Berlin",
        "development-only",
    )
    assert {item.kind for item in page.items} == {
        "geocode_request",
        "notification_delivery",
    }
    geocoding = next(item for item in page.items if item.kind == "geocode_request")
    assert geocoding.entity_name == "Venue 20"
    assert geocoding.organization_name == "Organization 10"
    assert geocoding.summary == "Geocoding fehlgeschlagen"
    assert geocoding.workflow_status == "failed" and geocoding.candidate_count == 0
    assert geocoding.entity_action and geocoding.entity_action.href == f"/venues/{uid(20)}"
    assert geocoding.href == f"/geocoding/{uid(850)}"
    delivery = next(item for item in page.items if item.kind == "notification_delivery")
    assert delivery.entity_name == "Organization 10"
    assert delivery.entity_action and delivery.entity_action.href == f"/organizations/{uid(10)}"
    payload = page.model_dump_json()
    for secret in (
        "secret@example.invalid",
        "Private subject",
        "private provider response",
        "not returned",
    ):
        assert secret not in payload


async def test_assignment_routes_auth_roster_and_safe_errors(
    database, admin_store, db_client, headers
):
    await provision_admin(database, uid(800))
    await add_finding(admin_store)
    assert (await db_client.get("/api/v1/admins")).status_code == 401
    roster = await db_client.get("/api/v1/admins", headers=headers)
    assert roster.status_code == 200
    assert roster.json() == {
        "items": [{"id": str(uid(800)), "login": "operator"}],
        "admin_timezone": "Europe/Berlin",
    }
    assert "password" not in roster.text
    response = await db_client.post(
        "/api/v1/assignments",
        headers=headers,
        json={"finding_id": "finding:one", "assigned_to_admin_id": str(uid(800))},
    )
    assert response.status_code == 201, response.text
    created = response.json()
    current = await db_client.get(
        "/api/v1/assignments", headers=headers, params={"finding_id": "finding:one"}
    )
    assert current.status_code == 200 and current.json()["id"] == created["id"]
    stale = await db_client.patch(
        f"/api/v1/assignments/{created['id']}",
        headers=headers,
        json={
            "version": 99,
            "assigned_to_admin_id": str(uid(800)),
            "status": "done",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "assignment_conflict"
    inbox = await db_client.get("/api/v1/inbox", headers=headers)
    assert inbox.status_code == 200, inbox.text
    assert inbox.json()["pagination"]["total"] == 1


@pytest.mark.parametrize(
    "body",
    [
        {"version": 1},
        {"version": 1, "status": None},
        {"version": 1, "assigned_to_admin_id": None},
        {"version": 1, "snoozed_until": "2026-09-25T09:00:00"},
        {"version": 1, "snoozed_until": "not-a-date"},
    ],
)
def test_snooze_patch_rejects_invalid_contract(body):
    with pytest.raises(ValidationError):
        AssignmentUpdate.model_validate(body)


async def test_snooze_api_versions_snapshots_timeline_and_unsnooze(
    database, admin_store, db_client, headers
):
    await provision_admin(database, uid(800))
    await add_finding(admin_store)
    created = await create_assignment(admin_store, creation(uid(800), due_at=NOW), "admin:test")
    url = f"/api/v1/assignments/{created.id}"
    until = datetime.now(UTC) + timedelta(days=3)
    payload = {"version": 1, "snoozed_until": until.isoformat()}
    assert (await db_client.patch(url, json=payload)).status_code == 401
    response = await db_client.patch(url, json=payload, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == 2 and body["status"] == "open"
    assert datetime.fromisoformat(body["snoozed_until"]) == until
    assert datetime.fromisoformat(body["due_at"]) == NOW
    assert (await db_client.patch(url, json=payload, headers=headers)).status_code == 409
    removed = await db_client.patch(
        url, json={"version": 2, "snoozed_until": None}, headers=headers
    )
    assert removed.status_code == 200 and removed.json()["version"] == 3
    assert removed.json()["snoozed_until"] is None
    unchanged = await db_client.patch(
        url, json={"version": 3, "snoozed_until": None}, headers=headers
    )
    assert unchanged.json()["version"] == 3
    events = (
        (
            await admin_store.execute(
                select(assignment_event)
                .where(assignment_event.c.assignment_id == created.id)
                .order_by(assignment_event.c.version)
            )
        )
        .mappings()
        .all()
    )
    assert [r["snoozed_until"] for r in events] == [None, until, None]
    assert [r["kind"] for r in events] == ["created", "updated", "updated"]
    assert [r["version"] for r in events] == [1, 2, 3]
    assert all(r["actor"] and r["due_at"] == NOW and r["status"] == "open" for r in events)
    await admin_store.rollback()
    # Page-size one exercises window comparisons before cursor/limit filtering.
    timeline_url = f"/api/v1/entities/event/{uid(30)}/timeline"
    timeline = (await db_client.get(timeline_url, params={"page_size": 1}, headers=headers)).json()
    assert timeline["items"][0]["kind"] == "assignment_unsnoozed"
    assert timeline["items"][0]["title"] == "Wiedervorlage aufgehoben"
    timeline = (
        await db_client.get(
            timeline_url,
            params={"page_size": 1, "cursor": timeline["cursor_pagination"]["next_cursor"]},
            headers=headers,
        )
    ).json()
    assert timeline["items"][0]["kind"] == "assignment_snoozed"
    assert "Europe/Berlin" in timeline["items"][0]["summary"]
    assert timeline["items"][0]["actor"]
    with pytest.raises(DBAPIError):
        await admin_store.execute(text("UPDATE admin.assignment_event SET snoozed_until=NULL"))
    await admin_store.rollback()
    with pytest.raises(DBAPIError):
        await admin_store.execute(text("DELETE FROM admin.assignment_event"))
    await admin_store.rollback()


@pytest.mark.parametrize("status", ["done", "cancelled"])
async def test_closed_assignment_cannot_snooze(database, admin_store, status):
    await provision_admin(database, uid(800))
    await add_finding(admin_store)
    created = await create_assignment(admin_store, creation(uid(800)), "admin:test")
    snoozed = await update_assignment(
        admin_store,
        created.id,
        AssignmentUpdate(version=1, snoozed_until=datetime.now(UTC) + timedelta(days=1)),
        "admin:test",
    )
    closed = await update_assignment(
        admin_store,
        created.id,
        AssignmentUpdate(version=snoozed.version, status=status),
        "admin:test",
    )
    assert closed.snoozed_until is None
    for extra in ({}, {"status": "open"}):
        with pytest.raises(APIError) as error:
            await update_assignment(
                admin_store,
                created.id,
                AssignmentUpdate(
                    version=closed.version,
                    snoozed_until=datetime.now(UTC) + timedelta(days=1),
                    **extra,
                ),
                "admin:test",
            )
        assert error.value.code == "assignment_task_closed"


@pytest.mark.parametrize("delta", [timedelta(seconds=-1), timedelta(days=366)])
async def test_snooze_requires_bounded_future(database, admin_store, delta):
    await provision_admin(database, uid(800))
    await add_finding(admin_store)
    created = await create_assignment(admin_store, creation(uid(800)), "admin:test")
    with pytest.raises(APIError) as error:
        await update_assignment(
            admin_store,
            created.id,
            AssignmentUpdate(version=1, snoozed_until=datetime.now(UTC) + delta),
            "admin:test",
        )
    assert error.value.code == "invalid_input"


async def test_snooze_revalidates_finding_task(database, admin_store):
    await provision_admin(database, uid(800))
    await add_finding(admin_store)
    created = await create_assignment(admin_store, creation(uid(800)), "admin:test")
    await admin_store.execute(finding.update().values(status="resolved"))
    await admin_store.commit()
    with pytest.raises(APIError) as error:
        await update_assignment(
            admin_store,
            created.id,
            AssignmentUpdate(version=1, snoozed_until=datetime.now(UTC) + timedelta(days=1)),
            "admin:test",
        )
    assert error.value.code == "assignment_task_closed"


@pytest.mark.parametrize("finding_days,assignment_days", [(3, 1), (1, 3)])
async def test_combined_snoozes_expire_without_mutation_and_remain_deduplicated(
    database, admin_store, db_connection, finding_days, assignment_days
):
    from app.admin_tables import assignment
    from app.schemas.checks import ReviewUpdate
    from app.services.checks import review

    await provision_admin(database, uid(800))
    await add_finding(admin_store)
    now = datetime.now(UTC)
    finding_until = now + timedelta(days=finding_days)
    assignment_until = now + timedelta(days=assignment_days)
    # Exercise the existing review service, including its unchanged reviewed event.
    reviewed = await review(
        admin_store,
        db_connection,
        ReviewUpdate(finding_id="finding:one", status="snoozed", snoozed_until=finding_until),
        "admin:reviewer",
        now,
    )
    assert reviewed.status == "snoozed"
    before = await inbox_page(
        admin_store, db_connection, InboxFilters(), now, "Europe/Berlin", f"admin:{uid(800)}"
    )
    assert not before.items and before.counts.snoozed == 1
    created = await create_assignment(admin_store, creation(uid(800)), "admin:test")
    await update_assignment(
        admin_store,
        created.id,
        AssignmentUpdate(version=1, snoozed_until=assignment_until),
        "admin:test",
    )
    for at in (now, now + timedelta(days=2)):
        active = await inbox_page(
            admin_store, db_connection, InboxFilters(), at, "Europe/Berlin", f"admin:{uid(800)}"
        )
        reminders = await inbox_page(
            admin_store,
            db_connection,
            InboxFilters(attention="snoozed"),
            at,
            "Europe/Berlin",
            f"admin:{uid(800)}",
        )
        assert not active.items and active.counts.snoozed == 1
        assert active.counts.critical == active.counts.mine == active.counts.unassigned == 0
        assert len(reminders.items) == reminders.pagination.total == 1
        assert reminders.items[0].snoozed_until == max(finding_until, assignment_until)
        assert reminders.items[0].assignment.id == created.id
    # At equality, both cease suppressing the task. Stored finding review state stays untouched.
    expired = await inbox_page(
        admin_store,
        db_connection,
        InboxFilters(),
        max(finding_until, assignment_until),
        "Europe/Berlin",
        f"admin:{uid(800)}",
    )
    assert len(expired.items) == 1 and expired.counts.snoozed == 0 and expired.counts.mine == 1
    assert expired.items[0].snoozed_until is None
    stored_finding = (await admin_store.execute(select(finding))).mappings().one()
    assert (
        stored_finding["status"] == "snoozed" and stored_finding["snoozed_until"] == finding_until
    )
    assert (
        await admin_store.execute(select(assignment.c.snoozed_until))
    ).scalar_one() == assignment_until
    await admin_store.rollback()
    # Removing organizational snooze never resets the finding's independent review.
    await update_assignment(
        admin_store, created.id, AssignmentUpdate(version=2, snoozed_until=None), "admin:test"
    )
    hidden = await inbox_page(
        admin_store, db_connection, InboxFilters(), now, "Europe/Berlin", f"admin:{uid(800)}"
    )
    assert not hidden.items and hidden.counts.snoozed == 1


async def test_expired_unassigned_finding_returns_without_recheck(admin_store, db_connection):
    await add_finding(admin_store)
    await admin_store.execute(finding.update().values(status="snoozed", snoozed_until=NOW))
    await admin_store.commit()
    page = await inbox_page(
        admin_store, db_connection, InboxFilters(), NOW, "Europe/Berlin", "admin:test"
    )
    assert len(page.items) == 1 and page.items[0].kind == "finding"
    assert page.counts.unassigned == 1 and page.counts.snoozed == 0


async def test_reminder_sort_pagination_counts_and_batched_queries(
    database, admin_store, db_connection
):
    from tests.test_timeline import CountedConnection

    await provision_admin(database, uid(800))
    now = datetime.now(UTC)
    assignments = []
    for number, days in enumerate([3, 1, 1]):
        identity = f"finding:{number}"
        await add_finding(admin_store, identity, field=f"field-{number}")
        created = await create_assignment(
            admin_store,
            AssignmentCreate(
                finding_id=identity, assigned_to_admin_id=uid(800), due_at=now - timedelta(hours=1)
            ),
            "admin:test",
        )
        value = await update_assignment(
            admin_store,
            created.id,
            AssignmentUpdate(version=1, snoozed_until=now + timedelta(days=days)),
            "admin:test",
        )
        assignments.append(value)
    counted_admin, counted_source = CountedConnection(admin_store), CountedConnection(db_connection)
    # Preserve the real transaction manager while counting SQL calls.
    counted_admin.begin = admin_store.begin
    first = await inbox_page(
        counted_admin,
        counted_source,
        InboxFilters(attention="snoozed", page_size=1),
        now,
        "Europe/Berlin",
        f"admin:{uid(800)}",
    )
    assert counted_admin.calls == 4 and counted_source.calls == 1
    assert first.counts.snoozed == 3 and first.counts.overdue == first.counts.critical == 0
    assert first.pagination.total == first.pagination.pages == 3
    ids = [first.items[0].id]
    for page in (2, 3):
        result = await inbox_page(
            admin_store,
            db_connection,
            InboxFilters(attention="snoozed", page_size=1, page=page),
            now,
            "Europe/Berlin",
            f"admin:{uid(800)}",
        )
        ids.append(result.items[0].id)
    assert ids == [
        f"assignment:{a.id}"
        for a in sorted(assignments, key=lambda a: (a.snoozed_until, str(a.id)))
    ]


@pytest.mark.parametrize(
    "now,expected_start,expected_end",
    [
        (
            datetime(2026, 3, 29, 12, tzinfo=UTC),
            "2026-03-28T23:00:00+00:00",
            "2026-03-29T22:00:00+00:00",
        ),
        (
            datetime(2026, 10, 25, 12, tzinfo=UTC),
            "2026-10-24T22:00:00+00:00",
            "2026-10-25T23:00:00+00:00",
        ),
    ],
)
def test_inbox_calendar_bounds_on_dst_days(now, expected_start, expected_end):
    from app.services.inbox import params

    values = params(InboxFilters(), now, "Europe/Berlin", "admin:test")
    assert values["day_start"] == datetime.fromisoformat(expected_start)
    assert values["day_end"] == datetime.fromisoformat(expected_end)


async def test_active_inbox_priority_critical_overdue_today_then_other(
    database, admin_store, db_connection
):
    await provision_admin(database, uid(800))
    now = datetime.now(UTC).replace(hour=10)
    rows = [
        ("warning", None),
        ("warning", now + timedelta(hours=1)),
        ("warning", now - timedelta(hours=1)),
        ("error", None),
    ]
    identifiers = []
    for number, (severity, due_at) in enumerate(rows):
        identity = f"priority:{number}"
        await add_finding(admin_store, identity, severity, field=f"field-{number}")
        value = await create_assignment(
            admin_store,
            AssignmentCreate(finding_id=identity, assigned_to_admin_id=uid(800), due_at=due_at),
            "admin:test",
        )
        identifiers.append(f"assignment:{value.id}")
    page = await inbox_page(
        admin_store, db_connection, InboxFilters(), now, "Europe/Berlin", f"admin:{uid(800)}"
    )
    assert [item.id for item in page.items] == list(reversed(identifiers))
