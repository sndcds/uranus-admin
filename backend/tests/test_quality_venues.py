from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.repositories.venues import list_missing_geolocation
from app.schemas.finding import FindingFilters, Severity
from app.services.quality.priority import finding_priority
from app.services.quality.venues import map_venue
from tests.conftest import uid


@pytest.mark.parametrize(
    "severity,published,soon,upcoming,expected",
    [
        (Severity.error, True, True, True, 1),
        (Severity.error, True, False, False, 2),
        (Severity.error, False, False, False, 3),
        (Severity.warning, True, True, True, 4),
        (Severity.warning, False, False, True, 4),
        (Severity.warning, False, False, False, 5),
        (Severity.info, True, True, True, 6),
    ],
)
def test_priority(severity, published, soon, upcoming, expected):
    assert finding_priority(severity, published=published, soon=soon, upcoming=upcoming) == expected


def test_mapping_does_not_fabricate_history():
    now = datetime(2026, 9, 14, tzinfo=UTC)
    row = {
        "uuid": uid(20),
        "name": "Hafenbühne",
        "org_uuid": uid(10),
        "organization_name": "Nord",
        "street": "Hafenstraße",
        "country": "DEU",
        "upcoming_event_date_count": 3,
        "upcoming_published_event_date_count": 2,
        "soon_published_event_date_count": 1,
    }
    finding = map_venue(row, now)
    assert finding.first_seen_at is None
    assert finding.last_seen_at == now
    assert finding.id == map_venue(row, now).id
    assert finding.severity == Severity.warning
    assert finding.address.street == "Hafenstraße"


@pytest.mark.integration
async def test_real_postgis_null_empty_valid_and_overrides(db_connection, settings, now):
    rows, total = await list_missing_geolocation(db_connection, settings, FindingFilters(), now)
    assert total == 2
    assert [row["uuid"] for row in rows] == [uid(20), uid(22)]
    assert rows[0]["upcoming_event_date_count"] == 6
    assert rows[0]["upcoming_published_event_date_count"] == 4
    assert rows[0]["soon_published_event_date_count"] == 2
    assert rows[1]["upcoming_event_date_count"] == 2
    assert rows[1]["upcoming_published_event_date_count"] == 0


@pytest.mark.integration
async def test_organization_filter_and_empty_page(db_connection, settings, now):
    rows, total = await list_missing_geolocation(
        db_connection, settings, FindingFilters(organization_id=uid(11)), now
    )
    assert total == 1 and rows[0]["uuid"] == uid(22)
    rows, total = await list_missing_geolocation(
        db_connection, settings, FindingFilters(page=3, page_size=1), now
    )
    assert rows == [] and total == 2


@pytest.mark.integration
async def test_today_time_boundary(db_connection, settings, now):
    from zoneinfo import ZoneInfo

    local = now.astimezone(ZoneInfo(settings.event_timezone))
    await db_connection.execute(
        text(
            "INSERT INTO uranus.event_date "
            "(uuid,event_uuid,start_date,start_time) VALUES (:id,:event,:day,'00:00')"
        ),
        {"id": uid(99), "event": uid(30), "day": local.date()},
    )
    rows, _ = await list_missing_geolocation(db_connection, settings, FindingFilters(), now)
    assert rows[0]["upcoming_event_date_count"] == 6
    await db_connection.execute(
        text("UPDATE uranus.event_date SET all_day=true WHERE uuid=:id"), {"id": uid(99)}
    )
    rows, _ = await list_missing_geolocation(db_connection, settings, FindingFilters(), now)
    assert rows[0]["upcoming_event_date_count"] == 7


@pytest.mark.integration
@pytest.mark.parametrize("path", ["/api/v1/findings", "/api/v1/quality/venues/missing-geolocation"])
async def test_quality_api(db_client, headers, path):
    response = await db_client.get(path, headers=headers, params={"page_size": 1})
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["items"]) == 1
    assert body["pagination"] == {"page": 1, "page_size": 1, "total": 2, "pages": 2}
    assert body["mode"] == "live"
    assert body["items"][0]["first_seen_at"] is None


@pytest.mark.integration
@pytest.mark.parametrize(
    "params",
    [
        {"severity": "error"},
        {"entity_type": "event"},
        {"rule": "unknown"},
        {"status": "reviewed"},
        {"status": "ignored"},
        {"status": "resolved"},
    ],
)
async def test_live_filters(db_client, headers, params):
    response = await db_client.get("/api/v1/findings", headers=headers, params=params)
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 0


@pytest.mark.integration
@pytest.mark.parametrize(
    "params",
    [
        {"severity": "fatal"},
        {"status": "bad"},
        {"page_size": 101},
        {"page": 0},
        {"organization_id": "' OR 1=1 --"},
    ],
)
async def test_invalid_filters(db_client, headers, params):
    response = await db_client.get("/api/v1/findings", headers=headers, params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_input"


def test_composite_entity_key_and_legacy_uuid_alias():
    from app.admin_tables import finding as table
    from app.schemas.finding import Finding

    original = map_venue(
        {
            "uuid": uid(20),
            "name": "Venue",
            "org_uuid": uid(10),
            "organization_name": "Org",
            "upcoming_event_date_count": 0,
            "upcoming_published_event_date_count": 0,
            "soon_published_event_date_count": 0,
        },
        datetime(2026, 9, 14, tzinfo=UTC),
    )
    assert original.entity_key == str(uid(20))
    assert original.entity_id == uid(20)
    data = original.model_dump(exclude={"entity_id"})
    for key in [f"partner-request:{uid(10)}:{uid(11)}", f"membership:{uid(10)}:{uid(1)}"]:
        composite = Finding.model_validate({**data, "entity_key": key})
        assert composite.entity_key == key
        assert composite.entity_id is None
    assert table.c.entity_key.name == "entity_id"  # Existing TEXT storage needs no migration.


@pytest.mark.parametrize("severity", list(Severity))
@pytest.mark.parametrize(
    "published,soon,upcoming",
    [(False, False, False), (False, False, True), (True, False, True), (True, True, True)],
)
def test_priority_score_is_explicit(severity, published, soon, upcoming):
    from app.services.quality.priority import priority_details

    result = priority_details(severity, published=published, soon=soon, upcoming=upcoming)
    assert (
        result["priority_score"]
        == (7 - result["priority"]) * 1000
        + 200 * published
        + 400 * (published and soon)
        + 100 * upcoming
    )
    assert ("published_soon" in result["priority_reasons"]) == (published and soon)
    assert f"severity_{severity}" in result["priority_reasons"]
