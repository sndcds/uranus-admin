from typing import TypedDict

from app.schemas.finding import Severity


def finding_priority(severity: Severity, *, published: bool, soon: bool, upcoming: bool) -> int:
    if severity == Severity.error:
        return 1 if published and soon else 2 if published else 3
    if severity == Severity.warning:
        return 4 if upcoming else 5
    return 6


class PriorityDetails(TypedDict):
    priority: int
    priority_score: int
    priority_reasons: list[str]


RELEVANCE_WEIGHTS = {"published": 200, "published_soon": 400, "upcoming_dates": 100}


def priority_details(
    severity: Severity, *, published: bool, soon: bool, upcoming: bool
) -> PriorityDetails:
    priority = finding_priority(severity, published=published, soon=soon, upcoming=upcoming)
    flags = {
        "published": published,
        "published_soon": published and soon,
        "upcoming_dates": upcoming,
    }
    return {
        "priority": priority,
        "priority_score": (7 - priority) * 1000
        + sum(RELEVANCE_WEIGHTS[key] for key, enabled in flags.items() if enabled),
        "priority_reasons": [f"severity_{severity}"]
        + [key for key, enabled in flags.items() if enabled],
    }


def venue_priority_score_sql() -> str:
    # Same discrete priority and relevance weights as every other rule. Counts are evidence,
    # not an additional hidden sorting criterion. All identifiers are source-code constants.
    return (
        "(CASE WHEN upcoming_event_date_count > 0 THEN 3000 ELSE 2000 END"
        f" + CASE WHEN upcoming_published_event_date_count > 0 THEN "
        f"{RELEVANCE_WEIGHTS['published']} ELSE 0 END"
        f" + CASE WHEN soon_published_event_date_count > 0 THEN "
        f"{RELEVANCE_WEIGHTS['published_soon']} ELSE 0 END"
        f" + CASE WHEN upcoming_event_date_count > 0 THEN "
        f"{RELEVANCE_WEIGHTS['upcoming_dates']} ELSE 0 END)"
    )
