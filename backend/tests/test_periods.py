from datetime import UTC, datetime, timedelta

import pytest

from app.services.periods import period_window


@pytest.mark.parametrize(
    "instant,expected",
    [
        ("2026-03-29T21:59:00+00:00", "2026-03-28T23:00:00+00:00"),
        ("2026-10-25T22:59:00+00:00", "2026-10-24T22:00:00+00:00"),
        ("2026-01-15T12:00:00+00:00", "2026-01-14T23:00:00+00:00"),
        ("2026-07-15T12:00:00+00:00", "2026-07-14T22:00:00+00:00"),
        ("2026-09-14T00:30:00+00:00", "2026-09-13T22:00:00+00:00"),
    ],
)
def test_today_calendar_midnight_across_dst(instant, expected):
    now = datetime.fromisoformat(instant)
    window = period_window("today", now, "Europe/Berlin")
    assert window.start == datetime.fromisoformat(expected)
    assert window.end == now
    assert window.start != period_window("24h", now, "Europe/Berlin").start


@pytest.mark.parametrize("period,hours", [("24h", 24), ("7d", 168), ("30d", 720), ("90d", 2160)])
def test_rolling_periods(period, hours):
    now = datetime(2026, 3, 29, 12, tzinfo=UTC)
    result = period_window(period, now, "Europe/Berlin")
    assert result.end - result.start == timedelta(hours=hours)


def test_naive_time_rejected():
    with pytest.raises(ValueError):
        period_window("today", datetime(2026, 9, 14), "Europe/Berlin")
