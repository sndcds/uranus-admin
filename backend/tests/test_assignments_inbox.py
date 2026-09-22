from datetime import UTC, datetime, timedelta

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
from app.services.inbox import inbox_page
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


async def add_finding(admin_store, identity="finding:one", severity="error"):
    await admin_store.execute(
        finding.insert().values(
            id=identity,
            rule="missing_description",
            severity=severity,
            entity_type="event",
            entity_key=str(uid(30)),
            field="description",
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

    mismatched = body.model_copy(update={"workflow_key": str(uid(851)), "entity_key": str(uid(21))})
    await admin_store.execute(
        geocode_request.insert().values(
            id=uid(851),
            entity_type="venue",
            entity_key=uid(20),
            source_fingerprint="c" * 64,
            query_fingerprint="d" * 64,
            status="failed",
            generation=1,
            query_version=1,
            scoring_version=1,
            attempt_count=1,
        )
    )
    await admin_store.commit()
    with pytest.raises(APIError) as mismatch:
        await create_assignment(admin_store, mismatched, "admin:test")
    assert mismatch.value.code == "assignment_task_invalid"


async def test_inbox_deduplicates_assignment_and_filters_mine(database, admin_store, db_connection):
    await provision_admin(database, uid(800))
    await add_finding(admin_store)
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
    assert roster.json() == {"items": [{"id": str(uid(800)), "login": "operator"}]}
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
