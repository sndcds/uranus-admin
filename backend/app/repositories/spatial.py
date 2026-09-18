"""Fixed predicates for authoritative source points. No admin joins or provider calls."""

from app.errors import APIError
from app.repositories.location import EFFECTIVE_VENUE_SQL
from app.repositories.temporal import EFFECTIVE_EVENT_DATE_END_SQL, TEMPORAL_COMPARISONS
from app.schemas.entities import TemporalFilter

SPATIAL_TYPES = frozenset({"organization", "venue", "space", "event", "event_date"})
SCOPE_SQL = "ST_GeomFromEWKB(:geo_scope_wkb)"


def spatial_predicate(kind: str, temporal: TemporalFilter | None = None) -> str:
    """Outer alias a.entity_key is code-owned. For events both conditions bind the SAME date."""
    point = "o.point" if kind == "organization" else "v.point"
    covered = f"{point} IS NOT NULL AND {point} && {SCOPE_SQL} AND ST_Covers({SCOPE_SQL},{point})"
    if kind == "organization":
        source, link = "uranus.organization o", "o.uuid=CAST(a.entity_key AS uuid)"
    elif kind == "venue":
        source, link = "uranus.venue v", "v.uuid=CAST(a.entity_key AS uuid)"
    elif kind == "space":
        source = "uranus.space s JOIN uranus.venue v ON v.uuid=s.venue_uuid"
        link = "s.uuid=CAST(a.entity_key AS uuid)"
    elif kind in {"event", "event_date"}:
        source = (
            "uranus.event_date d JOIN uranus.event e ON e.uuid=d.event_uuid "
            f"JOIN uranus.venue v ON v.uuid={EFFECTIVE_VENUE_SQL}"
        )
        link = ("d.event_uuid" if kind == "event" else "d.uuid") + "=CAST(a.entity_key AS uuid)"
        if temporal:
            link += (
                f" AND {EFFECTIVE_EVENT_DATE_END_SQL} {TEMPORAL_COMPARISONS[temporal]} "
                "CAST(:temporal_now AS timestamptz)"
            )
    else:
        raise APIError(422, "invalid_input", "Geo filtering is not supported for this entity.")
    return f"EXISTS (SELECT 1 FROM {source} WHERE {link} AND {covered})"
