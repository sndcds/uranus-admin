"""Event-date end semantics shared by entity lists and autocomplete.

Date/time columns are local wall times in settings.event_timezone. PostgreSQL
converts them to instants before comparing with the request's aware UTC clock.
Aliases a (entity), d (date) and e (event) are fixed application SQL.
"""

from app.errors import APIError
from app.repositories.location import EFFECTIVE_SPACE_SQL, EFFECTIVE_VENUE_SQL
from app.schemas.entities import TemporalFilter

# End-of-day is the final microsecond before the next local midnight (also on DST days).
# An end_time without end_date applies to start_date. Without either, use the start.
EFFECTIVE_EVENT_DATE_END_SQL = """(
    CASE
      WHEN d.all_day IS TRUE OR (d.end_date IS NOT NULL AND d.end_time IS NULL)
        THEN ((COALESCE(d.end_date,d.start_date) + 1)::timestamp
              AT TIME ZONE :event_tz) - INTERVAL '1 microsecond'
      ELSE ((COALESCE(d.end_date,d.start_date)
             + COALESCE(d.end_time,d.start_time,TIME '00:00')) AT TIME ZONE :event_tz)
    END
)"""

ENTITY_DATE_LINKS = {
    "event": "d.event_uuid = CAST(a.entity_key AS uuid)",
    "organization": "e.org_uuid = CAST(a.entity_key AS uuid)",
    "venue": f"({EFFECTIVE_VENUE_SQL}) = CAST(a.entity_key AS uuid)",
    "space": f"({EFFECTIVE_SPACE_SQL}) = CAST(a.entity_key AS uuid)",
}
TEMPORAL_COMPARISONS = {"upcoming": ">=", "past": "<"}


def temporal_predicate(kind: str, temporal: TemporalFilter | None) -> str:
    if temporal is None:
        return "TRUE"
    if kind not in ENTITY_DATE_LINKS:
        raise APIError(422, "invalid_input", "Temporal filtering is not supported for this entity.")
    return f"""EXISTS (
        SELECT 1 FROM uranus.event_date d JOIN uranus.event e ON e.uuid=d.event_uuid
        WHERE {ENTITY_DATE_LINKS[kind]}
          AND {EFFECTIVE_EVENT_DATE_END_SQL} {TEMPORAL_COMPARISONS[temporal]}
              CAST(:temporal_now AS timestamptz)
    )"""
