from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.errors import APIError
from app.repositories.creation_sources import RECORD_TABLES
from app.repositories.dashboard import check_status, new_records
from app.repositories.spatial import SPATIAL_TYPES
from app.schemas.dashboard import DashboardSummary, NewRecords, Period, QualityCounts
from app.services.checks import persisted_counts
from app.services.geo.membership import filter_live_findings
from app.services.geo.scopes import ResolvedGeoScope
from app.services.periods import period_window
from app.services.quality.engine import scan


async def get_summary(
    connection: AsyncConnection,
    settings: Settings,
    period: Period,
    now: datetime,
    admin: AsyncConnection | None = None,
    geo: ResolvedGeoScope | None = None,
) -> DashboardSummary:
    source_timezone = settings.uranus_timestamp_timezone
    if source_timezone is None:
        raise APIError(
            503,
            "source_timezone_unconfigured",
            "The Uranus timestamp storage timezone must be confirmed and configured.",
        )
    window = period_window(period, now, settings.admin_timezone)
    wkb = geo.ewkb if geo else None
    counts, unknown = await new_records(connection, window, source_timezone, wkb)
    if admin is not None:
        quality, urgent = await persisted_counts(admin, connection, wkb)
    else:
        results = await scan(connection, settings, now)
        items = await filter_live_findings(
            connection, [item for result in results for item in result.findings], wkb
        )
        urgent = sum(
            item.priority <= 2 or "published_soon" in item.priority_reasons for item in items
        )
        quality = QualityCounts(
            total=len(items),
            warnings=sum(item.severity == "warning" for item in items),
            errors=sum(item.severity == "error" for item in items),
            info=sum(item.severity == "info" for item in items),
            rules=[result.rule for result in results],
            rule_counts={
                result.rule: sum(item.rule == result.rule for item in items) for result in results
            },
            mode="live",
        )
    return DashboardSummary(
        period=period,
        from_at=window.start,
        to_at=window.end,
        admin_timezone=settings.admin_timezone,
        source_timestamp_timezone=source_timezone,
        new_records=NewRecords(total=sum(counts.values()), **counts),
        geo_scope_id=geo.area.id if geo else None,
        new_record_scopes={
            key: "geo" if geo and table in SPATIAL_TYPES else "global"
            for key, table in RECORD_TABLES.items()
        },
        scoped_new_records_total=sum(
            value for key, value in counts.items() if RECORD_TABLES[key] in SPATIAL_TYPES
        )
        if geo
        else None,
        global_new_records_total=sum(
            value for key, value in counts.items() if RECORD_TABLES[key] not in SPATIAL_TYPES
        )
        if geo
        else None,
        images_without_created_at=unknown,
        urgent_findings=urgent,
        quality=quality,
        check_status=await check_status(admin) if admin is not None else None,
    )
