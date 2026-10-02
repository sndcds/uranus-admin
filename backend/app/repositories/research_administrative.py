"""Resolve administrative meaning from persisted, operator-imported boundaries.

No name heuristics, geocoder metadata inference or source writes. This adapter
keeps the existing public ResearchArea contract unchanged.
"""

from app.repositories.research_areas import ResolvedResearchArea
from app.research.catalog import REGION_PREFIX
from app.research.geography import (
    AdministrativeAreaRef,
    AdministrativeIdentity,
    AdministrativeLevel,
    BoundaryReference,
    OfficialCodeSystem,
)


def administrative_reference(area: ResolvedResearchArea) -> AdministrativeAreaRef:
    row = area.area
    level: AdministrativeLevel = row.area_type
    # Imported municipality identity has priority: independent cities can use
    # level 6; city states can use level 4. Never demote these to districts/states.
    if row.area_type == "region":
        if row.osm_admin_level == 2:
            level = "country"
        elif row.country_code == "DE" and row.osm_admin_level == 4:
            level = "state"
        elif row.country_code == "DE" and row.osm_admin_level == 6:
            level = "district"
    country = AdministrativeIdentity("country", row.country_code, row.country_code, "ISO-3166-1")
    state_code = next((code for code, iso in REGION_PREFIX.items() if iso == row.region_code), None)
    state = (
        AdministrativeIdentity("state", "DE", state_code, "DE-state")
        if row.country_code == "DE" and state_code
        else None
    )
    code: str | None = None
    system: OfficialCodeSystem | None = None
    parent = None
    ancestors: tuple[AdministrativeIdentity, ...] = ()
    if level == "country":
        code, system = row.country_code, "ISO-3166-1"
    else:
        ancestors = (country,)
        if level == "state":
            code, system = (state_code, "DE-state") if state else (None, None)
            parent = country
        elif level in {"district", "municipality"}:
            if state:
                ancestors = (state, country)
                if level == "district":
                    parent = state
            if level == "municipality" and row.country_code == "DE" and area.municipality_key:
                code, system = area.municipality_key, "DE-AGS"
    # District codes and municipality->district parent IDs are not stored today.
    # Do not derive either from names or pretend that a state is the direct parent.
    return AdministrativeAreaRef(
        name=row.name,
        level=level,
        country_code=row.country_code,
        official_code=code,
        code_system=system,
        resolved_id=row.id,
        boundary=BoundaryReference(row.id),
        parent=parent,
        ancestors=ancestors,
    )
