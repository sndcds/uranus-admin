"""Verified get-event-dates.sql semantics, shared by previews and graph queries.

Aliases d (date) and e (parent event) are fixed application SQL, never request data.
A venue override deliberately stops inheritance of the event's space.
"""

EFFECTIVE_VENUE_SQL = "COALESCE(d.venue_uuid,e.venue_uuid)"
EFFECTIVE_SPACE_SQL = (
    "CASE WHEN d.venue_uuid IS NOT NULL THEN d.space_uuid "
    "ELSE COALESCE(d.space_uuid,e.space_uuid) END"
)
