"""Closed external policy; unregistered rules and entities are internal only."""

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any

from app.config import Settings

TEMPLATE_VERSION = 1  # Semantic recommendation version, not CSS or code version.
SEVERITY = {"info": 0, "warning": 1, "error": 2}


@dataclass(frozen=True)
class ExternalPolicy:
    entities: frozenset[str]
    template: str
    delivery: str = "digest"


EXTERNAL_POLICY = {
    "event_without_dates": ExternalPolicy(frozenset({"event"}), "event_without_dates"),
    "event_without_location": ExternalPolicy(frozenset({"event"}), "event_without_location"),
    "event_date_without_location": ExternalPolicy(
        frozenset({"event_date"}), "event_date_without_location"
    ),
    "url_syntax": ExternalPolicy(
        frozenset({"event", "event_date", "event_link", "organization", "venue", "space"}),
        "url_syntax",
    ),
    "venue_missing_logo": ExternalPolicy(frozenset({"venue"}), "venue_missing_logo"),
    "organization_missing_logo": ExternalPolicy(
        frozenset({"organization"}), "organization_missing_logo"
    ),
}


def stage(days_until: int, settings: Settings) -> int:
    return (
        3
        if days_until <= settings.notification_urgent_days
        else 2
        if days_until <= settings.notification_important_days
        else 1
    )


def next_date(dates: list[dict[str, Any]], local: datetime) -> dict[str, Any] | None:
    from app.repositories.temporal import is_upcoming_start

    return min(
        (row for row in dates if is_upcoming_start(row, local)),
        key=lambda row: (
            row["start_date"],
            row["start_time"] is None,
            row["start_time"] or time.min,
            str(row["uuid"]),
        ),
        default=None,
    )
