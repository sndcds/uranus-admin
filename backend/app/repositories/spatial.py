"""Fixed predicates for authoritative source points. No admin joins or provider calls."""

from app.errors import APIError
from app.repositories.location import EFFECTIVE_VENUE_SQL
from app.repositories.temporal import EFFECTIVE_EVENT_DATE_END_SQL, TEMPORAL_COMPARISONS
from app.schemas.entities import TemporalFilter

SPATIAL_TYPES = frozenset({"organization", "venue", "space", "event", "event_date"})
SCOPE_SQL = "ST_GeomFromEWKB(:geo_scope_wkb)"


def spatial_predicate(
    kind: str,
    temporal: TemporalFilter | None = None,
    *,
    key_expression: str = "CAST(a.entity_key AS uuid)",
) -> str:
    """Identifiers/expressions are code-owned, never request input. Same date for time + geo."""
    point = "geo_o.point" if kind == "organization" else "geo_v.point"
    covered = f"{point} IS NOT NULL AND {point} && {SCOPE_SQL} AND ST_Covers({SCOPE_SQL},{point})"
    if kind == "organization":
        source, link = "uranus.organization geo_o", f"geo_o.uuid={key_expression}"
    elif kind == "venue":
        source, link = "uranus.venue geo_v", f"geo_v.uuid={key_expression}"
    elif kind == "space":
        source = "uranus.space geo_s JOIN uranus.venue geo_v ON geo_v.uuid=geo_s.venue_uuid"
        link = f"geo_s.uuid={key_expression}"
    elif kind in {"event", "event_date"}:
        effective_venue = EFFECTIVE_VENUE_SQL.replace("d.", "geo_d.").replace("e.", "geo_e.")
        effective_end = EFFECTIVE_EVENT_DATE_END_SQL.replace("d.", "geo_d.").replace("e.", "geo_e.")
        source = (
            "uranus.event_date geo_d JOIN uranus.event geo_e ON geo_e.uuid=geo_d.event_uuid "
            f"JOIN uranus.venue geo_v ON geo_v.uuid={effective_venue}"
        )
        link = ("geo_d.event_uuid" if kind == "event" else "geo_d.uuid") + f"={key_expression}"
        if temporal:
            link += (
                f" AND {effective_end} {TEMPORAL_COMPARISONS[temporal]} "
                "CAST(:temporal_now AS timestamptz)"
            )
    else:
        raise APIError(422, "invalid_input", "Geo filtering is not supported for this entity.")
    return f"EXISTS (SELECT 1 FROM {source} WHERE {link} AND {covered})"


def mixed_spatial_predicate() -> str:
    """Guard UUID casts with CASE: nonspatial Activity keys can be composite text."""
    branches = " ".join(
        f"WHEN '{kind}' THEN {spatial_predicate(kind)}" for kind in sorted(SPATIAL_TYPES)
    )
    kinds = ",".join(f"'{kind}'" for kind in sorted(SPATIAL_TYPES))
    return f"(a.entity_type IN ({kinds}) AND CASE a.entity_type {branches} ELSE FALSE END)"
