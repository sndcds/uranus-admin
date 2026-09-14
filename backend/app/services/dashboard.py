from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.errors import APIError
from app.repositories.dashboard import new_records
from app.schemas.dashboard import DashboardSummary, NewRecords, Period, QualityCounts
from app.services.periods import period_window
from app.services.quality.engine import scan


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
    results = await scan(connection, settings, now)
    items = [item for result in results for item in result.findings]
    total = len(items)
    urgent = sum(item.priority <= 2 or "published_soon" in item.priority_reasons for item in items)
    return DashboardSummary(
        period=period,
        from_at=window.start,
        to_at=window.end,
        admin_timezone=settings.admin_timezone,
        source_timestamp_timezone=source_timezone,
        new_records=NewRecords(total=sum(counts.values()), **counts),
        images_without_created_at=unknown,
        urgent_findings=urgent,
        quality=QualityCounts(
            total=total,
            warnings=sum(item.severity == "warning" for item in items),
            errors=sum(item.severity == "error" for item in items),
            info=sum(item.severity == "info" for item in items),
            rules=[result.rule for result in results],
        ),
    )
