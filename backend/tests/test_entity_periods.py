from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.api import entities as api
from app.database import get_connection
from app.main import create_app
from app.services.periods import period_window
from tests.conftest import uid

# Verified source identifiers, fixture records and projections; no request-owned identifiers.
ENTITIES = [
    ("event", "events", "uranus.event", 30),
    ("user", "users", 'uranus."user"', 1),
    ("organization", "organizations", "uranus.organization", 10),
    ("venue", "venues", "uranus.venue", 20),
    ("space", "spaces", "uranus.space", 25),
    ("image", "images", "uranus.pluto_image", 60),
]


@pytest.fixture
async def period_client(db_connection, settings, monkeypatch):
    clock = {"now": datetime(2026, 1, 15, 12, tzinfo=UTC)}

    class Clock:
        @staticmethod
        def now(tz):
            return clock["now"]

    monkeypatch.setattr(api, "datetime", Clock)

    async def connection():
        yield db_connection

    app = create_app(settings)
    app.dependency_overrides[get_connection] = connection
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, clock


@pytest.mark.integration
@pytest.mark.parametrize("kind,section,table,key", ENTITIES)
@pytest.mark.parametrize("period", [None, "today", "24h", "7d", "30d", "90d"])
@pytest.mark.parametrize("month", [1, 7])
@pytest.mark.parametrize("source_timezone", ["UTC", "Europe/Berlin"])
async def test_all_entity_period_boundaries_on_both_endpoints(
    period_client,
    db_connection,
    settings,
    headers,
    kind,
    section,
    table,
    key,
    period,
    month,
    source_timezone,
):
    client, clock = period_client
    now = datetime(2026, month, 15, 12, tzinfo=UTC)
    clock["now"] = now
    settings.uranus_timestamp_timezone = source_timezone
    window = period_window(period or "90d", now, "Europe/Berlin")
    stamps = [
        window.start - timedelta(microseconds=1),
        window.start,
        now - timedelta(microseconds=1),
        now,
        now + timedelta(days=1),
    ]
    if kind == "image":
        stamps.append(None)
    for stamp in stamps:
        await db_connection.execute(
            text(f"UPDATE {table} SET created_at=:stamp WHERE uuid=:key"),
            {
                "key": uid(key),
                "stamp": stamp.astimezone(ZoneInfo(source_timezone)).replace(tzinfo=None)
                if stamp
                else None,
            },
        )
        expected = period is None or stamp is not None and window.start <= stamp < window.end
        for path, extra in [(section, {}), ("entity-search", {"entity_type": kind})]:
            response = await client.get(
                f"/api/v1/{path}",
                headers=headers,
                params={"q": str(uid(key)), **extra, **({"period": period} if period else {})},
            )
            assert response.status_code == 200, response.text
            assert bool(response.json()["items"]) == expected, (period, stamp, response.text)
            if path == section:
                assert response.json()["pagination"]["total"] == int(expected)


@pytest.mark.integration
@pytest.mark.parametrize("kind,section,table,key", ENTITIES)
async def test_period_combines_with_search_status_temporal_and_organization(
    period_client,
    db_connection,
    settings,
    headers,
    kind,
    section,
    table,
    key,
):
    client, clock = period_client
    now = clock["now"]
    await db_connection.execute(
        text(f"UPDATE {table} SET created_at=:stamp WHERE uuid=:key"),
        {"stamp": (now - timedelta(days=2)).replace(tzinfo=None), "key": uid(key)},
    )
    await db_connection.execute(
        text(
            "UPDATE uranus.event SET release_status='released',space_uuid=:space WHERE uuid=:event"
        ),
        {"space": uid(25), "event": uid(30)},
    )
    await db_connection.execute(
        text(
            "UPDATE uranus.event_date SET start_date=:day,end_date=NULL,start_time=NULL,"
            "end_time=NULL,venue_uuid=NULL,space_uuid=NULL WHERE event_uuid=:event"
        ),
        {"day": (now + timedelta(days=365)).date(), "event": uid(30)},
    )
    await db_connection.execute(
        text('UPDATE uranus."user" SET is_active=true WHERE uuid=:key'), {"key": uid(1)}
    )
    await db_connection.execute(
        text(
            "INSERT INTO uranus.pluto_image_link "
            "(pluto_image_uuid,context,context_uuid,identifier) "
            "VALUES (:image,'organization',:org,'period-test')"
        ),
        {"image": uid(60), "org": uid(10)},
    )
    status = {"event": "released", "user": "active"}.get(kind)
    temporal = kind in {"event", "organization", "venue", "space"}
    params = {
        "q": str(uid(key)),
        "period": "7d",
        "organization_id": str(uid(10)),
        **({"status": status} if status else {}),
        **({"temporal": "upcoming"} if temporal else {}),
    }
    variants = [
        ({}, True),
        ({"period": "today"}, False),
        ({"organization_id": str(uid(999))}, False),
        ({"q": "no-match"}, False),
    ]
    if temporal:
        variants.append(({"temporal": "past"}, False))
    if status:
        variants.append(({"status": "draft" if kind == "event" else "inactive"}, False))
    for path, extra in [(section, {}), ("entity-search", {"entity_type": kind})]:
        for change, expected in variants:
            response = await client.get(
                f"/api/v1/{path}", headers=headers, params={**params, **extra, **change}
            )
            assert response.status_code == 200, response.text
            assert bool(response.json()["items"]) == expected, (kind, change, response.text)


@pytest.mark.parametrize("period", ["custom", "unknown", "all", "", "7D", "bad"])
async def test_period_validation(client, headers, period):
    async def unused_connection():
        yield None

    client._transport.app.dependency_overrides[get_connection] = unused_connection
    for path in [*(entity[1] for entity in ENTITIES), "entity-search"]:
        response = await client.get(
            f"/api/v1/{path}",
            headers=headers,
            params={
                "period": period,
                **({"q": "xx", "entity_type": "user"} if path == "entity-search" else {}),
            },
        )
        assert response.status_code == 422


@pytest.mark.integration
async def test_created_period_is_read_only(db_client, headers):
    for path in [*(entity[1] for entity in ENTITIES), "entity-search"]:
        response = await db_client.get(
            f"/api/v1/{path}",
            headers=headers,
            params={
                "period": "7d",
                **({"q": "fixture", "entity_type": "user"} if path == "entity-search" else {}),
            },
        )
        assert response.status_code == 200, response.text


async def test_creation_period_requires_source_timezone(client, settings, headers):
    settings.uranus_timestamp_timezone = None

    async def unused_connection():
        yield None

    client._transport.app.dependency_overrides[get_connection] = unused_connection
    for path in [*(entity[1] for entity in ENTITIES), "entity-search"]:
        response = await client.get(
            f"/api/v1/{path}",
            headers=headers,
            params={
                "period": "today",
                **({"q": "xx", "entity_type": "user"} if path == "entity-search" else {}),
            },
        )
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "source_timezone_unconfigured"
