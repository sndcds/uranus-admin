from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.errors import APIError
from app.repositories.dashboard import new_records
from app.repositories.venues import quality_counts
from app.schemas.dashboard import DashboardSummary, NewRecords, Period, QualityCounts
from app.services.periods import period_window


async def get_summary(
    connection: AsyncConnection, settings: Settings, period: Period, now: datetime
) -> DashboardSummary:
    source_timezone = settings.uranus_timestamp_timezone
    if source_timezone is None:
        raise APIError(
            503,
            "source_timezone_unconfigured",
            "The Uranus timestamp storage timezone must be confirmed and configured.",
        )
    window = period_window(period, now, settings.admin_timezone)
    counts, unknown = await new_records(connection, window, source_timezone)
    total, urgent = await quality_counts(connection, settings, now)
    return DashboardSummary(
        period=period,
        from_at=window.start,
        to_at=window.end,
        admin_timezone=settings.admin_timezone,
        source_timestamp_timezone=source_timezone,
        new_records=NewRecords(total=sum(counts.values()), **counts),
        images_without_created_at=unknown,
        urgent_findings=urgent,
        quality=QualityCounts(total=total, warnings=total),
    )
