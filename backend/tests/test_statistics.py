from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.errors import APIError
from app.repositories.dashboard import new_records
from app.schemas.statistics import StatisticsFilters
from app.services.periods import PeriodWindow
from app.services.statistics import (
    automatic_interval,
    bucket_windows,
    get_statistics,
    statistics_window,
)
from tests.conftest import uid

NOW = datetime(2026, 9, 16, 14, 7, tzinfo=UTC)


@pytest.mark.parametrize(
    "period,interval,buckets",
    [("24h", "15m", 97), ("7d", "1h", 169), ("30d", "6h", 121), ("90d", "1d", 91)],
)
def test_presets_and_clipped_natural_buckets(period, interval, buckets):
    window = statistics_window(StatisticsFilters(period=period), NOW, "Europe/Berlin")
    assert automatic_interval(window) == interval
    points = bucket_windows(window, interval, "Europe/Berlin")
    assert len(points) == buckets
    assert points[0].start == window.start and points[-1].end == NOW
    assert all(a.end == b.start for a, b in zip(points, points[1:], strict=False))
    assert all(p.start < p.end for p in points)
    local = points[1].start.astimezone(ZoneInfo("Europe/Berlin"))
    assert local.minute % 15 == 0
    if interval == "1d":
        assert local.hour == 0
    if interval == "6h":
        assert local.hour in (0, 6, 12, 18)


@pytest.mark.parametrize("day,hours", [("2026-03-29", 23), ("2026-10-25", 25)])
def test_dst_calendar_buckets_and_repeated_hours(day, hours):
    start = datetime.fromisoformat(day).replace(tzinfo=ZoneInfo("Europe/Berlin"))
    end = start + timedelta(days=1)
    window = PeriodWindow(start.astimezone(UTC), end.astimezone(UTC))
    hourly = bucket_windows(window, "1h", "Europe/Berlin")
    assert len(hourly) == hours
    assert sum((p.end - p.start).total_seconds() for p in hourly) == hours * 3600
    assert bucket_windows(window, "1d", "Europe/Berlin") == [window]
    six = bucket_windows(window, "6h", "Europe/Berlin")
    assert len(six) == 4
    assert all(p.start.astimezone(ZoneInfo("Europe/Berlin")).hour in (0, 6, 12, 18) for p in six)


@pytest.mark.parametrize(
    "query",
    [
        {"period": "bad"},
        {"interval": "bad"},
        {"period": "custom"},
        {"from_at": NOW},
        {"from_at": NOW, "to_at": NOW},
        {"from_at": NOW, "to_at": NOW + timedelta(days=366)},
        {"period": "7d", "from_at": NOW, "to_at": NOW + timedelta(days=1)},
        {"from_at": datetime(2026, 9, 1), "to_at": NOW},
        {"sql": "anything"},
    ],
)
def test_invalid_ranges(query):
    with pytest.raises(ValidationError):
        StatisticsFilters.model_validate(query)


def test_manual_bucket_limit():
    window = PeriodWindow(NOW - timedelta(days=90), NOW)
    with pytest.raises(APIError) as error:
        bucket_windows(window, "15m", "Europe/Berlin")
    assert error.value.status == 422


async def test_counts_match_dashboard_and_invitation_semantics(db_connection, settings, now):
    await db_connection.execute(
        text(
            "UPDATE uranus.organization_member_link SET created_at=:old, invited_at=:invited, "
            "has_joined=true"
        ),
        {
            "old": (now - timedelta(days=10)).replace(tzinfo=None),
            "invited": (now - timedelta(minutes=40)).replace(tzinfo=None),
        },
    )
    result = await get_statistics(
        db_connection, settings, StatisticsFilters(compare="previous"), now
    )
    series = {s.entity_type: s for s in result.series}
    counts, _ = await new_records(db_connection, PeriodWindow(result.from_at, result.to_at), "UTC")
    for singular, plural in [
        ("user", "users"),
        ("organization", "organizations"),
        ("venue", "venues"),
        ("space", "spaces"),
        ("event", "events"),
        ("partner_request", "partner_requests"),
    ]:
        assert series[singular].total == counts[plural]
    assert series["team_invitation"].total == 1
    assert counts["team_memberships"] == 0
    assert all(s.total == sum(p.count for p in s.points) for s in result.series)
    assert all(any(p.count == 0 for p in s.points) for s in result.series)
    assert all(s.previous_total == 0 for s in result.series)
    assert result.previous_to_at == result.from_at
    assert result.previous_to_at - result.previous_from_at == result.to_at - result.from_at
    assert len(result.recent) == 7
    assert all(item.entity_type not in ("image", "event_date") for item in result.recent)
    assert "password" not in result.model_dump_json() and "email" not in result.model_dump_json()
    await db_connection.execute(text("UPDATE uranus.organization_member_link SET invited_at=NULL"))
    result = await get_statistics(db_connection, settings, StatisticsFilters(), now)
    assert result.series[-1].total == 0  # never fall back to created_at


@pytest.mark.parametrize(
    "timezone,stamp", [("UTC", "2026-09-01 00:00"), ("Europe/Berlin", "2026-09-01 02:00")]
)
async def test_half_open_boundaries_and_source_timezone(db_connection, settings, timezone, stamp):
    settings.uranus_timestamp_timezone = timezone
    await db_connection.execute(
        text(
            'INSERT INTO uranus."user" (uuid,email,password_hash,created_at) '
            "VALUES (:id,'statistics@example.invalid','not-a-hash',:stamp)"
        ),
        {"id": uid(9990), "stamp": datetime.fromisoformat(stamp)},
    )
    start = datetime(2026, 9, 1, tzinfo=UTC)
    filters = StatisticsFilters(from_at=start, to_at=start + timedelta(hours=1))
    result = await get_statistics(db_connection, settings, filters, NOW)
    assert result.series[0].total == 1
    assert [p.count for p in result.series[0].points] == [1, 0, 0, 0]
    assert result.recent[0].created_at == start
    await db_connection.execute(
        text('UPDATE uranus."user" SET created_at=:stamp WHERE uuid=:id'),
        {"id": uid(9990), "stamp": datetime.fromisoformat(stamp) + timedelta(hours=1)},
    )
    result = await get_statistics(db_connection, settings, filters, NOW)
    assert result.series[0].total == 0


async def test_dst_fallback_counts_both_repeated_hours_once(db_connection, settings):
    await db_connection.execute(
        text(
            "INSERT INTO uranus.organization (uuid,name,created_at) VALUES "
            "(:a,'before fallback','2026-10-25 00:30'),(:b,'after fallback','2026-10-25 01:30')"
        ),
        {"a": uid(9991), "b": uid(9992)},
    )
    result = await get_statistics(
        db_connection,
        settings,
        StatisticsFilters(
            from_at=datetime(2026, 10, 25, tzinfo=UTC),
            to_at=datetime(2026, 10, 25, 3, tzinfo=UTC),
            interval="1h",
        ),
        NOW,
    )
    assert [p.count for p in result.series[1].points] == [1, 1, 0]


async def test_statistics_api_contract_and_validation(db_client, headers, settings):
    response = await db_client.get("/api/v1/statistics/entities?period=7d", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["series"]) == 7 and body["interval"] == "1h"
    assert body["timezone"] == "Europe/Berlin"
    for query in [
        "period=invalid",
        "period=custom",
        "period=90d&interval=15m",
        "interval=bad",
        "from_at=2026-01-01&to_at=2026-02-01",
    ]:
        response = await db_client.get("/api/v1/statistics/entities?" + query, headers=headers)
        assert response.status_code == 422, response.text
    settings.uranus_timestamp_timezone = None
    response = await db_client.get("/api/v1/statistics/entities", headers=headers)
    assert response.status_code == 503


async def test_activity_statistics_basis_uses_invitation_time(db_connection, settings, now):
    from app.repositories.activity import activity_page
    from app.schemas.activity import ActivityFilters

    await db_connection.execute(
        text("UPDATE uranus.organization_member_link SET created_at=:old, invited_at=:recent"),
        {
            "old": (now - timedelta(days=50)).replace(tzinfo=None),
            "recent": (now - timedelta(minutes=10)).replace(tzinfo=None),
        },
    )
    result = await activity_page(
        db_connection,
        settings,
        ActivityFilters(creation_basis="statistics", entity_type="team_membership", period="24h"),
        now,
    )
    assert result.pagination.total == 1
    assert result.items[0].created_at == now - timedelta(minutes=10)
