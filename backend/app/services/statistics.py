from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.errors import APIError
from app.repositories.statistics import aggregate, recent_entities
from app.schemas.statistics import (
    EntityStatisticsResponse,
    StatisticsFilters,
    StatisticsInterval,
)
from app.services.periods import PeriodWindow, period_window


def statistics_window(filters: StatisticsFilters, now: datetime, timezone: str) -> PeriodWindow:
    if filters.from_at and filters.to_at:
        return PeriodWindow(filters.from_at.astimezone(UTC), filters.to_at.astimezone(UTC))
    if filters.period is None or filters.period == "custom":
        return period_window("24h", now, timezone)
    return period_window(filters.period, now, timezone)


def automatic_interval(window: PeriodWindow) -> StatisticsInterval:
    days = (window.end - window.start).total_seconds() / 86400
    if days <= 1:
        return "15m"
    if days <= 7:
        return "1h"
    if days <= 30:
        return "6h"
    return "1d"


def bucket_windows(
    window: PeriodWindow, interval: StatisticsInterval, timezone: str
) -> list[PeriodWindow]:
    """Natural local boundaries, clipped to the exact half-open request range.

    Sub-hour/hour steps advance in UTC to preserve both repeated DST hours.
    Six-hour/day steps advance on the local calendar (23/25-hour days).
    Only boundaries are generated here; PostgreSQL performs all record aggregation.
    """
    local = window.start.astimezone(ZoneInfo(timezone))
    if interval == "15m":
        cursor = local.replace(minute=local.minute // 15 * 15, second=0, microsecond=0)
    elif interval == "1h":
        cursor = local.replace(minute=0, second=0, microsecond=0)
    else:
        hour = local.hour // 6 * 6 if interval == "6h" else 0
        cursor = local.replace(hour=hour, minute=0, second=0, microsecond=0, fold=0)
    windows = []
    while cursor.astimezone(UTC) < window.end:
        if interval in ("15m", "1h"):
            next_at = cursor.astimezone(UTC) + timedelta(minutes=15 if interval == "15m" else 60)
        else:
            next_at = cursor + timedelta(hours=6 if interval == "6h" else 24)
        start = max(cursor.astimezone(UTC), window.start)
        end = min(next_at.astimezone(UTC), window.end)
        if start < end:
            windows.append(PeriodWindow(start, end))
        if len(windows) > 500:
            raise APIError(422, "statistics_bucket_limit", "Choose a coarser interval (max 500).")
        cursor = next_at
    return windows


async def get_statistics(
    connection: AsyncConnection, settings: Settings, filters: StatisticsFilters, now: datetime
) -> EntityStatisticsResponse:
    if settings.uranus_timestamp_timezone is None:
        raise APIError(503, "source_timezone_unconfigured", "Source timezone must be configured.")
    window = statistics_window(filters, now, settings.admin_timezone)
    interval = automatic_interval(window) if filters.interval == "auto" else filters.interval
    windows = bucket_windows(window, interval, settings.admin_timezone)
    series = await aggregate(connection, windows, settings.uranus_timestamp_timezone)
    previous = None
    if filters.compare:
        previous = PeriodWindow(window.start - (window.end - window.start), window.start)
        # Only previous totals are displayed; one aggregate bucket avoids redundant series.
        prior = await aggregate(connection, [previous], settings.uranus_timestamp_timezone)
        for current, old in zip(series, prior, strict=True):
            current.previous_total = old.total
    return EntityStatisticsResponse(
        period="custom" if filters.from_at else filters.period or "24h",
        from_at=window.start,
        to_at=window.end,
        timezone=settings.admin_timezone,
        interval=interval,
        observed_at=now,
        previous_from_at=previous.start if previous else None,
        previous_to_at=previous.end if previous else None,
        series=series,
        recent=await recent_entities(connection, window, settings.uranus_timestamp_timezone),
    )
