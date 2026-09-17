from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.repositories.created_period import require_timezone
from app.repositories.event_content import aggregate_event_content
from app.schemas.event_content import EventContentFilters, EventContentStatistics
from app.services.periods import period_window, previous_window


def percent(count: int, total: int) -> float:
    return round(count * 100 / total, 2) if total else 0.0


def coverage(assigned: int, total: int) -> dict[str, int | float]:
    return {
        "events_with_assignment": assigned,
        "events_without_assignment": total - assigned,
        "coverage_percent": percent(assigned, total),
    }


async def get_event_content(
    connection: AsyncConnection, settings: Settings, filters: EventContentFilters, now: datetime
) -> EventContentStatistics:
    timezone = require_timezone(settings)
    window = (
        None
        if filters.period == "all"
        else period_window(filters.period, now, settings.admin_timezone)
    )
    previous = previous_window(window) if window and filters.compare else None
    rows = await aggregate_event_content(connection, window, previous, timezone, filters.status)
    rankings: dict[str, Any] = {}
    current_coverage, old_coverage = {}, {}
    for row in rows:
        dimension, total = row["dimension"], row["event_count"]
        current_coverage[dimension] = coverage(row["with_assignment"], total)
        if previous:
            old_coverage[dimension] = coverage(
                row["previous_with_assignment"], row["previous_total"]
            )
        ranking = rankings.setdefault(
            dimension,
            {
                "distinct_assignment_count": row["distinct_assignments"],
                "items": [],
            },
        )
        if row["id"] is None:
            continue
        item = {
            "id": row["id"],
            "name": row["name"],
            "rank": row["rank"],
            "event_count": row["assigned_count"],
            "event_share_percent": percent(row["assigned_count"], total),
        }
        if previous:
            old_share = percent(row["previous_assigned_count"], row["previous_total"])
            item.update(
                {
                    "previous_rank": row["previous_rank"],
                    "rank_delta": row["previous_rank"] - row["rank"]
                    if row["previous_rank"]
                    else None,
                    "previous_event_count": row["previous_assigned_count"],
                    "count_delta": row["assigned_count"] - row["previous_assigned_count"],
                    "previous_share_percent": old_share,
                    "share_delta_percentage_points": round(
                        item["event_share_percent"] - old_share, 2
                    ),
                }
            )
        ranking["items"].append(item)
    return EventContentStatistics.model_validate(
        {
            "period": filters.period,
            "from_at": window.start if window else None,
            "to_at": window.end if window else None,
            "observed_at": now,
            "timezone": settings.admin_timezone,
            "status": filters.status,
            "event_count": rows[0]["event_count"],
            "coverage": current_coverage,
            **rankings,
            "comparison": {
                "from_at": previous.start,
                "to_at": previous.end,
                "event_count": rows[0]["previous_total"],
                "coverage": old_coverage,
            }
            if previous
            else None,
        }
    )
