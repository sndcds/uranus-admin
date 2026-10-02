"""Geocoder is authoritative; ambiguity and role mismatches are never auto-corrected."""

import hashlib
from typing import Literal, cast

from app.clients.research_geocoder import ResearchGeocoderClient
from app.errors import APIError
from app.research.internal_plan import (
    AdministrativeAreaRef,
    AdministrativeLevel,
    AreaRequest,
    ResolvedBoundary,
)
from app.schemas.research_administrative import AdministrativePlace

OSM_TYPES = {"node": "N", "way": "W", "relation": "R"}


def resolution_error(code: str) -> APIError:
    return APIError(
        422, "research_area_" + code, "Select an unambiguous area with the requested level."
    )


def select_candidate(items: list[AdministrativePlace], request: AreaRequest) -> AdministrativePlace:
    # No substring heuristics or first-hit selection. Metadata identifies each object;
    # exact canonical names only disambiguate amongst otherwise eligible candidates.
    eligible = [
        p
        for p in items
        if p.administrative_level != "unknown"
        and (request.country_code is None or p.country_code == request.country_code)
        and (request.expected_level is None or request.expected_level in p.administrative_levels)
    ]
    if not eligible:
        raise resolution_error("level_mismatch" if items else "no_match")
    exact = [
        p
        for p in eligible
        if p.name and p.name.strip().casefold() == request.query.strip().casefold()
    ]
    choices = exact or eligible
    identities = {(p.osm_type, p.osm_id) for p in choices}
    if len(identities) != 1 or None in next(iter(identities)):
        raise resolution_error("ambiguous")
    return choices[0]


def resolved_boundary(
    place: AdministrativePlace, expected: AdministrativeLevel | None
) -> ResolvedBoundary:
    level = expected or place.administrative_level
    if level == "unknown" or level not in place.administrative_levels:
        raise resolution_error("level_mismatch")
    if (
        not place.name
        or not place.country_code
        or not place.osm_type
        or place.osm_id is None
        or place.boundary is None
    ):
        raise resolution_error("boundary_unavailable")
    osm_type = cast(Literal["N", "W", "R"], OSM_TYPES[place.osm_type])
    geometry = place.boundary.model_dump_json()
    return ResolvedBoundary(
        AdministrativeAreaRef(
            name=place.name,
            level=level,
            country_code=place.country_code,
            official_code=place.official_code,
            official_code_type=place.official_code_type,
            osm_type=osm_type,
            osm_id=place.osm_id,
            area_id=f"osm:{osm_type}:{place.osm_id}:{level}",
            boundary_reference="sha256:" + hashlib.sha256(geometry.encode()).hexdigest(),
        ),
        geometry,
    )


async def resolve_administrative_area(
    client: ResearchGeocoderClient, request: AreaRequest
) -> ResolvedBoundary:
    selected = select_candidate(await client.search_administrative(request.query), request)
    assert selected.osm_type is not None and selected.osm_id is not None
    lookup = await client.administrative_boundary(OSM_TYPES[selected.osm_type], selected.osm_id)
    if lookup is None:
        raise resolution_error("no_match")
    if lookup.country_code != selected.country_code or (
        request.country_code is not None and lookup.country_code != request.country_code
    ):
        raise resolution_error("level_mismatch")
    # With no requested role, lookup must still confirm the search classification.
    return resolved_boundary(
        lookup, request.expected_level or cast(AdministrativeLevel, selected.administrative_level)
    )
