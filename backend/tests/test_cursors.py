import base64
import json
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.admin_tables import finding
from app.errors import APIError
from app.repositories.activity import activity_page
from app.schemas.activity import ActivityFilters
from app.schemas.cursor import ActivityCursor, FindingCursor, decode, encode, scope
from app.schemas.finding import FindingFilters
from app.services.checks import persisted_page
from tests.conftest import uid


@pytest.mark.integration
async def test_activity_cursor_identical_timestamps_and_insert(db_connection, settings, now):
    await db_connection.execute(
        text("UPDATE uranus.organization SET created_at=:stamp"),
        {"stamp": now.replace(tzinfo=None) - timedelta(minutes=1)},
    )
    filters = ActivityFilters(period="7d", page_size=1, cursor="start")
    original = await activity_page(
        db_connection, settings, ActivityFilters(period="7d", page_size=100), now
    )
    seen = []
    first = await activity_page(db_connection, settings, filters, now)
    seen.extend((i.entity_type, i.entity_key) for i in first.items)
    await db_connection.execute(
        text("INSERT INTO uranus.organization(uuid,name,created_at) VALUES(:id,'New',:stamp)"),
        {"id": uid(9901), "stamp": now.replace(tzinfo=None) - timedelta(seconds=1)},
    )
    page = first
    while page.cursor_pagination.has_more:
        filters.cursor = page.cursor_pagination.next_cursor
        page = await activity_page(db_connection, settings, filters, now + timedelta(hours=1))
        assert page.from_at == first.from_at and page.to_at == first.to_at
        seen.extend((i.entity_type, i.entity_key) for i in page.items)
    assert seen == [(i.entity_type, i.entity_key) for i in original.items]
    assert len(seen) == len(set(seen))


@pytest.mark.integration
async def test_unknown_timestamps_keyset(db_connection, settings, now):
    for key in (9902, 9903):
        await db_connection.execute(
            text(
                "INSERT INTO uranus.pluto_image(uuid,file_name,created_at) VALUES(:id,'x.jpg',NULL)"
            ),
            {"id": uid(key)},
        )
    filters = ActivityFilters(timestamp_state="unknown", cursor="start", page_size=1)
    seen = []
    while True:
        page = await activity_page(db_connection, settings, filters, now)
        seen.extend(i.entity_key for i in page.items)
        assert all(i.created_at is None for i in page.items)
        if not page.cursor_pagination.has_more:
            break
        filters.cursor = page.cursor_pagination.next_cursor
    assert len(seen) == len(set(seen)) == 3
    assert seen == sorted(seen)


@pytest.mark.integration
async def test_findings_cursor_ties_insert_and_scope(admin_store, now):
    async def insert(key):
        async with admin_store.begin():
            await admin_store.execute(
                finding.insert().values(
                    id=key,
                    rule="rule",
                    severity="warning",
                    entity_type="venue",
                    entity_key=key,
                    field="test",
                    message="test",
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )

    for key in ("b", "c", "d"):
        await insert(key)
    filters = FindingFilters(cursor="start", page_size=1)
    first = await persisted_page(admin_store, filters, now)
    await insert("a")
    seen = [first.items[0].id]
    page = first
    while page.cursor_pagination.has_more:
        filters.cursor = page.cursor_pagination.next_cursor
        page = await persisted_page(admin_store, filters, now)
        seen.extend(i.id for i in page.items)
    assert seen == ["b", "c", "d"]
    with pytest.raises(APIError) as exc:
        await persisted_page(
            admin_store,
            FindingFilters(cursor=first.cursor_pagination.next_cursor, severity="error"),
            now,
        )
    assert exc.value.status == 422


@pytest.mark.integration
@pytest.mark.parametrize(
    "query", ["cursor=garbage", "cursor=%%%", "cursor=start&page=1", "cursor=start&page_size=101"]
)
async def test_cursor_validation_http(admin_store, db_client, headers, query):
    for endpoint in ("dashboard/activity", "findings"):
        response = await db_client.get(f"/api/v1/{endpoint}?{query}", headers=headers)
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] == "invalid_input"


def test_cursor_endpoint_type_and_scope_validation(now):
    filters = ActivityFilters(cursor="start")
    valid = ActivityCursor(
        scope=scope(filters),
        entity_type="event",
        entity_key=str(uid(30)),
        created_at=now,
        from_at=now - timedelta(days=1),
        to_at=now,
    )
    assert decode(encode(valid), ActivityCursor, scope(filters)) == valid
    bad = valid.model_dump(mode="json")
    for change in (
        {"entity_type": "password"},
        {"endpoint": "findings"},
        {"version": 2},
        {"scope": "a" * 64},
        {"secret": "x"},
    ):
        token = base64.urlsafe_b64encode(json.dumps({**bad, **change}).encode()).decode()
        with pytest.raises(APIError):
            decode(token, ActivityCursor, scope(filters))
    with pytest.raises(APIError):
        decode(encode(valid), FindingCursor, scope(filters))
