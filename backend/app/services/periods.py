from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.schemas.periods import PresetPeriod


@dataclass(frozen=True)
class PeriodWindow:
    start: datetime
    end: datetime


def period_window(period: PresetPeriod, now: datetime, timezone: str) -> PeriodWindow:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    end = now.astimezone(UTC)
    if period == "today":
        zone = ZoneInfo(timezone)
        start = datetime.combine(end.astimezone(zone).date(), time.min, zone).astimezone(UTC)
    elif period == "24h":
        start = end - timedelta(hours=24)
    else:
        start = end - timedelta(days={"7d": 7, "30d": 30, "90d": 90}[period])
    return PeriodWindow(start=start, end=end)


def previous_window(window: PeriodWindow) -> PeriodWindow:
    """Immediately preceding range with the same elapsed duration, including today."""
    return PeriodWindow(window.start - (window.end - window.start), window.start)
