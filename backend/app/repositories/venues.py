from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.schemas.finding import FindingFilters, FindingStatus, Severity
from app.services.quality.priority import venue_priority_score_sql

RULE = "venue_missing_geolocation"
QUALITY_SQL = Path(__file__).with_name("sql").joinpath("venue_missing_geolocation.sql").read_text()


def query_parameters(
    settings: Settings, now: datetime, organization_id: UUID | None = None
) -> dict[str, Any]:
    local = now.astimezone(ZoneInfo(settings.event_timezone))
    return {
        "organization_id": organization_id,
        "local_date": local.date(),
        "local_time": local.time().replace(tzinfo=None),
        "soon_end": local.date() + timedelta(days=settings.upcoming_days),
    }


def matches_live_rule(filters: FindingFilters) -> bool:
    return (
        filters.severity in (None, Severity.warning)
        and filters.rule in (None, RULE)
        and filters.entity_type in (None, "venue")
        and filters.status in (None, FindingStatus.open)
    )


async def list_missing_geolocation(
    connection: AsyncConnection, settings: Settings, filters: FindingFilters, now: datetime
) -> tuple[list[dict[str, Any]], int]:
    if not matches_live_rule(filters):
        return [], 0
    params = query_parameters(settings, now, filters.organization_id)
    # Fixed SQL structure only; all user values are bound parameters.
    total = int(
        (
            await connection.execute(
                text("SELECT COUNT(*) FROM (" + QUALITY_SQL + ") AS findings"), params
            )
        ).scalar_one()
    )
    params.update(limit=filters.page_size, offset=(filters.page - 1) * filters.page_size)
    result = await connection.execute(
        text(
            "SELECT * FROM ("
            + QUALITY_SQL
            + """
        ) AS findings
        ORDER BY """
            + venue_priority_score_sql()
            + """ DESC, uuid
        LIMIT :limit OFFSET :offset
        """
        ),
        params,
    )
    return [dict(row) for row in result.mappings()], total


async def quality_counts(
    connection: AsyncConnection, settings: Settings, now: datetime
) -> tuple[int, int]:
    row = (
        (
            await connection.execute(
                text(
                    "SELECT COUNT(*) AS total, COUNT(*) FILTER "
                    "(WHERE soon_published_event_date_count > 0) AS urgent FROM ("
                    + QUALITY_SQL
                    + ") AS findings"
                ),
                query_parameters(settings, now),
            )
        )
        .mappings()
        .one()
    )
    return int(row["total"]), int(row["urgent"])
