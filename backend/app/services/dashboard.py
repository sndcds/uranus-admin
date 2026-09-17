from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.errors import APIError
from app.repositories.dashboard import check_status, new_records
from app.schemas.dashboard import DashboardSummary, NewRecords, Period, QualityCounts
from app.services.checks import persisted_counts
from app.services.periods import period_window
from app.services.quality.engine import scan


async def get_summary(
    connection: AsyncConnection,
    settings: Settings,
    period: Period,
    now: datetime,
    admin: AsyncConnection | None = None,
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
    if admin is not None:
        quality, urgent = await persisted_counts(admin)
    else:
        results = await scan(connection, settings, now)
        items = [item for result in results for item in result.findings]
        urgent = sum(
            item.priority <= 2 or "published_soon" in item.priority_reasons for item in items
        )
        quality = QualityCounts(
            total=len(items),
            warnings=sum(item.severity == "warning" for item in items),
            errors=sum(item.severity == "error" for item in items),
            info=sum(item.severity == "info" for item in items),
            rules=[result.rule for result in results],
            rule_counts={result.rule: len(result.findings) for result in results},
            mode="live",
        )
    return DashboardSummary(
        period=period,
        from_at=window.start,
        to_at=window.end,
        admin_timezone=settings.admin_timezone,
        source_timestamp_timezone=source_timezone,
        new_records=NewRecords(total=sum(counts.values()), **counts),
        images_without_created_at=unknown,
        urgent_findings=urgent,
        quality=quality,
        check_status=await check_status(admin) if admin is not None else None,
    )
