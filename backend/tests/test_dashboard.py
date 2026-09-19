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
    assert body["quality"]["total"] == 11
    assert body["quality"]["warnings"] == 11
    assert body["urgent_findings"] == 6
    assert body["quality"]["rule_counts"]["venue_missing_logo"] == 3
    assert body["quality"]["rule_counts"]["organization_missing_logo"] == 2
    assert body["quality"]["rule_counts"]["logo_unsupported_format"] == 0
    assert body["quality"]["rule_counts"]["postal_code_whitespace"] == 0
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


@pytest.mark.integration
@pytest.mark.parametrize("status", ["success", "failed", "running", "queued"])
async def test_dashboard_persisted_check_status(admin_store, db_client, headers, now, status):
    from app.admin_tables import check_run

    async with admin_store.begin():
        await admin_store.execute(
            check_run.insert(),
            [
                dict(
                    id=uid(801),
                    started_at=now - timedelta(hours=2),
                    finished_at=now - timedelta(hours=1),
                    status="success",
                    rule_count=19,
                    finding_count=7,
                ),
                dict(
                    id=uid(802),
                    started_at=now,
                    finished_at=now if status in {"failed", "success"} else None,
                    status=status,
                    rule_count=19,
                    finding_count=9,
                ),
            ],
        )
    response = await db_client.get("/api/v1/dashboard/summary", headers=headers)
    assert response.status_code == 200, response.text
    state = response.json()["check_status"]
    assert state["latest_run"]["id"] == str(uid(802))
    assert state["latest_run"]["status"] == status
    assert state["latest_run"]["finding_count"] == 9
    assert state["last_successful_run"]["id"] == str(uid(802 if status == "success" else 801))


@pytest.mark.integration
async def test_dashboard_check_status_empty_and_deterministic(admin_store, now):
    from app.admin_tables import check_run
    from app.repositories.dashboard import check_status

    async with admin_store.begin():
        empty = await check_status(admin_store)
        assert empty.latest_run is None and empty.last_successful_run is None
        for key in (803, 801, 802):
            await admin_store.execute(
                check_run.insert().values(
                    id=uid(key),
                    started_at=now,
                    finished_at=now,
                    status="success",
                    rule_count=2,
                    finding_count=1,
                )
            )
        state = await check_status(admin_store)
        assert state.latest_run.id == uid(803)
        assert state.last_successful_run.id == uid(803)
