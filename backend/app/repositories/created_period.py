"""Shared, parameterized created-at filtering of fixed entity projections."""

from datetime import datetime
from typing import Any

from app.config import Settings
from app.errors import APIError
from app.schemas.periods import PresetPeriod
from app.services.periods import period_window


def require_timezone(settings: Settings) -> str:
    if settings.uranus_timestamp_timezone is None:
        raise APIError(503, "source_timezone_unconfigured", "Source timezone must be configured.")
    return settings.uranus_timestamp_timezone


def created_period_filter(
    period: PresetPeriod | None, settings: Settings, now: datetime
) -> tuple[str, dict[str, Any]]:
    if period is None:
        return "TRUE", {}
    window = period_window(period, now, settings.admin_timezone)
    return (
        "a.created_at AT TIME ZONE :created_tz >= :period_start "
        "AND a.created_at AT TIME ZONE :created_tz < :period_end",
        {
            "created_tz": require_timezone(settings),
            "period_start": window.start,
            "period_end": window.end,
        },
    )
