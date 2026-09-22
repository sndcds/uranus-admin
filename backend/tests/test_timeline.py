from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import insert, text
from sqlalchemy.exc import DBAPIError

from app.admin_tables import finding, finding_event
from app.repositories.timeline import timeline_page
from app.schemas.timeline import TimelineFilters
from tests.conftest import uid

pytestmark = pytest.mark.integration


class CountedConnection:
    def __init__(self, connection):
        self.connection = connection
        self.calls = 0

    async def execute(self, *args, **kwargs):
        self.calls += 1
        return await self.connection.execute(*args, **kwargs)


def finding_values(now, *, identity: str, entity_key: str) -> dict[str, object]:
    return {
        "id": identity,
        "rule": "venue_missing_geolocation",
        "severity": "warning",
        "entity_type": "venue",
        "entity_key": entity_key,
        "field": "point",
        "message": "Standort fehlt.",
        "first_seen_at": now - timedelta(hours=3),
        "last_seen_at": now,
        "status": "open",
    }


def event_values(
    found: dict[str, object], *, event_id, kind: str, occurred_at, **extra
) -> dict[str, object]:
    return {
        "id": event_id,
        "finding_id": found["id"],
        "entity_type": found["entity_type"],
        "entity_key": found["entity_key"],
        "kind": kind,
        "occurred_at": occurred_at,
        "status": found["status"],
        "rule": found["rule"],
        "severity": found["severity"],
        "field": found["field"],
        "message": found["message"],
        "actor": None,
        "comment": None,
        "assigned_to": None,
        "snoozed_until": None,
        "exception_reason": None,
        **extra,
    }


async def test_timeline_aggregates_orders_and_paginates_verified_events(
    admin_store, db_client, headers, now
):
    key = str(uid(20))
    found = finding_values(now, identity="timeline-finding", entity_key=key)
    first_id = uid(700)
    second_id = uid(701)
    async with admin_store.begin():
        await admin_store.execute(insert(finding).values(**found))
        await admin_store.execute(
            insert(finding_event),
            [
                event_values(found, event_id=first_id, kind="detected", occurred_at=now),
                event_values(
                    found,
                    event_id=second_id,
                    kind="reviewed",
                    occurred_at=now,
                    actor="admin:reviewer",
                    comment="Adresse mit dem Träger klären.",
                ),
            ],
        )

    url = f"/api/v1/entities/venue/{key}/timeline"
    first = await db_client.get(url, params={"page_size": 2}, headers=headers)
    assert first.status_code == 200
    body = first.json()
    assert body["entity_type"] == "venue" and body["entity_key"] == key
    assert [item["id"] for item in body["items"]] == [
        f"finding:{second_id}",
        f"finding:{first_id}",
    ]
    assert body["items"][0]["kind"] == "finding_reviewed"
    assert body["items"][0]["actor"] == "admin:reviewer"
    assert "Adresse" in body["items"][0]["summary"]
    assert body["items"][0]["metadata"]["severity"] == "warning"
    assert body["items"][0]["href"].startswith("/findings?")
    assert body["cursor_pagination"]["has_more"] is True

    cursor = body["cursor_pagination"]["next_cursor"]
    second = await db_client.get(url, params={"page_size": 2, "cursor": cursor}, headers=headers)
    assert second.status_code == 200
    second_ids = {item["id"] for item in second.json()["items"]}
    assert not second_ids.intersection(item["id"] for item in body["items"])
    assert any(item["kind"] == "source_created" for item in second.json()["items"])


async def test_timeline_never_synthesizes_missing_source_timestamps(
    admin_store, db_client, headers
):
    del admin_store  # ensure the admin schema is present for the aggregate query
    response = await db_client.get(f"/api/v1/entities/image/{uid(61)}/timeline", headers=headers)
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["cursor_pagination"] == {
        "page_size": 25,
        "next_cursor": None,
        "has_more": False,
    }


async def test_timeline_rejects_unknown_entities_and_invalid_or_cross_scope_cursors(
    admin_store, db_client, headers
):
    del admin_store
    missing = await db_client.get(f"/api/v1/entities/venue/{uid(999)}/timeline", headers=headers)
    assert missing.status_code == 404
    invalid_type = await db_client.get(
        f"/api/v1/entities/password/{uid(20)}/timeline", headers=headers
    )
    assert invalid_type.status_code == 422
    invalid_key = await db_client.get("/api/v1/entities/venue/not-a-uuid/timeline", headers=headers)
    assert invalid_key.status_code == 422
    malformed = await db_client.get(
        f"/api/v1/entities/venue/{uid(20)}/timeline?cursor=private", headers=headers
    )
    assert malformed.status_code == 422

    page = await db_client.get(
        f"/api/v1/entities/organization/{uid(10)}/timeline?page_size=1", headers=headers
    )
    cursor = page.json()["cursor_pagination"]["next_cursor"]
    assert cursor
    wrong_scope = await db_client.get(
        f"/api/v1/entities/organization/{uid(11)}/timeline",
        params={"cursor": cursor, "page_size": 1},
        headers=headers,
    )
    assert wrong_scope.status_code == 422
    wrong_size = await db_client.get(
        f"/api/v1/entities/organization/{uid(10)}/timeline",
        params={"cursor": cursor, "page_size": 2},
        headers=headers,
    )
    assert wrong_size.status_code == 422


async def test_timeline_requires_authentication(admin_store, db_client):
    del admin_store
    response = await db_client.get(f"/api/v1/entities/venue/{uid(20)}/timeline")
    assert response.status_code == 401


async def test_timeline_uses_a_fixed_number_of_queries(admin_store, db_connection, settings, now):
    source = CountedConnection(db_connection)
    admin = CountedConnection(admin_store)
    page = await timeline_page(
        source,  # type: ignore[arg-type]
        admin,  # type: ignore[arg-type]
        settings,
        "organization",
        uid(10),
        TimelineFilters(page_size=50),
        now,
    )
    assert page.items
    assert source.calls == 2
    assert admin.calls == 1


async def test_finding_events_are_append_only_for_runtime(admin_store):
    found = finding_values(
        datetime.now(UTC),
        identity="append-only-finding",
        entity_key=str(uid(20)),
    )
    event_id = uuid4()
    async with admin_store.begin():
        await admin_store.execute(insert(finding).values(**found))
        await admin_store.execute(
            insert(finding_event).values(
                **event_values(
                    found,
                    event_id=event_id,
                    kind="detected",
                    occurred_at=found["first_seen_at"],
                )
            )
        )
    for statement in (
        "UPDATE admin.finding_event SET message='rewritten'",
        "DELETE FROM admin.finding_event",
        "TRUNCATE admin.finding_event",
    ):
        with pytest.raises(DBAPIError):
            await admin_store.execute(text(statement))
        await admin_store.rollback()
