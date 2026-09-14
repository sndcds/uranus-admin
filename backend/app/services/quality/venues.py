import logging
from datetime import datetime
from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.repositories import venues
from app.schemas.finding import Address, Finding, FindingFilters, FindingPage, Pagination, Severity
from app.services.quality.priority import finding_priority

logger = logging.getLogger("admin.quality")


def map_venue(row: dict[str, Any], observed_at: datetime) -> Finding:
    count = int(row["upcoming_event_date_count"])
    published = int(row["upcoming_published_event_date_count"])
    soon = int(row["soon_published_event_date_count"])
    return Finding(
        id=f"{venues.RULE}:venue:{row['uuid']}:point",
        rule=venues.RULE,
        severity=Severity.warning,
        priority=finding_priority(
            Severity.warning, published=published > 0, soon=soon > 0, upcoming=count > 0
        ),
        entity_type="venue",
        entity_id=row["uuid"],
        entity_name=row["name"],
        organization_id=row["org_uuid"],
        organization_name=row["organization_name"],
        field="point",
        message=f"Geoposition fehlt; betroffen sind {count} kommende Termine "
        f"(davon {published} veröffentlicht).",
        address=Address.model_validate(row),
        last_seen_at=observed_at,
        upcoming_event_date_count=count,
        upcoming_published_event_date_count=published,
        soon_published_event_date_count=soon,
    )


async def get_findings(
    connection: AsyncConnection, settings: Settings, filters: FindingFilters, now: datetime
) -> FindingPage:
    started = perf_counter()
    try:
        rows, total = await venues.list_missing_geolocation(connection, settings, filters, now)
        return FindingPage(
            items=[map_venue(row, now) for row in rows],
            observed_at=now,
            pagination=Pagination(
                page=filters.page,
                page_size=filters.page_size,
                total=total,
                pages=(total + filters.page_size - 1) // filters.page_size,
            ),
        )
    finally:
        logger.info(
            "quality_check",
            extra={"rule": venues.RULE, "duration_ms": round((perf_counter() - started) * 1000, 2)},
        )
