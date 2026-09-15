from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.repositories.dashboard import new_records
from app.services.periods import PeriodWindow
from tests.conftest import uid


@pytest.mark.integration
async def test_dashboard_real_counts(db_client, headers):
    response = await db_client.get("/api/v1/dashboard/summary?mode=live", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["new_records"] == {
        "total": 20,
        "organizations": 2,
        "venues": 3,
        "spaces": 1,
        "events": 0,
        "event_dates": 10,
        "users": 1,
        "partner_requests": 1,
        "team_memberships": 1,
        "images": 1,
    }
    assert body["images_without_created_at"] == 1
    assert body["quality"]["total"] == 2
    assert body["quality"]["warnings"] == 2
    assert body["urgent_findings"] == 1
    assert body["check_status"] is None


@pytest.mark.integration
async def test_unknown_source_timezone_fails_closed(db_client, settings, headers):
    settings.uranus_timestamp_timezone = None
    response = await db_client.get("/api/v1/dashboard/summary?mode=live", headers=headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_timezone_unconfigured"


@pytest.mark.integration
async def test_naive_source_timezone_and_half_open_boundaries(db_connection):
    start = datetime(2026, 9, 1, 0, tzinfo=UTC)
    end = start + timedelta(hours=1)
    # 02:00 naive Berlin means 00:00 UTC in September. Include start, exclude end.
    await db_connection.execute(
        text(
            "INSERT INTO uranus.pluto_image (uuid,file_name,created_at) "
            "VALUES (:a,'start.jpg','2026-09-01 02:00'),(:b,'end.jpg','2026-09-01 03:00')"
        ),
        {"a": uid(70), "b": uid(71)},
    )
    counts, _ = await new_records(db_connection, PeriodWindow(start, end), "Europe/Berlin")
    assert counts["images"] == 1
    counts, _ = await new_records(db_connection, PeriodWindow(start, end), "UTC")
    assert counts["images"] == 0
