"""TRANSITIONAL metadata adapter for the existing research_area schema.

Explicit persisted district/municipality types win. Only legacy `region` rows
need country/OSM-level interpretation until ingestion/geocoder metadata stores
an authoritative level. Keep that knowledge, including SQL prefiltering and code
conversion, here; domain models, the resolver and executor must not duplicate it.
No provider calls, name heuristics, new country mappings or guessed district IDs.
"""

from dataclasses import dataclass

from app.repositories.research_areas import ResolvedResearchArea
from app.research.catalog import REGION_PREFIX
from app.research.geography import AdministrativeIdentity, AdministrativeLevel, OfficialCodeSystem

# One compatibility rule set shared by candidate SQL and loaded-row metadata.
_LEGACY_REGION_LEVELS: tuple[tuple[str | None, int, AdministrativeLevel], ...] = (
    (None, 2, "country"),
    ("DE", 4, "state"),
    ("DE", 6, "district"),
)


@dataclass(frozen=True, slots=True)
class AdministrativeMetadata:
    level: AdministrativeLevel
    country_code: str
    official_code: str | None
    code_system: OfficialCodeSystem | None
    parent: AdministrativeIdentity | None = None
    ancestors: tuple[AdministrativeIdentity, ...] = ()


def administrative_level_sql() -> str:
    """Fixed application-owned projection; no planner/user values become SQL."""
    rules = " ".join(
        f"WHEN osm_admin_level={number}"
        + (f" AND country_code='{country}'" if country else "")
        + f" THEN '{level}'"
        for country, number, level in _LEGACY_REGION_LEVELS
    )
    return (
        "CASE WHEN area_type <> 'region' THEN area_type ELSE CASE "
        + rules
        + " ELSE 'region' END END"
    )


def administrative_metadata(area: ResolvedResearchArea) -> AdministrativeMetadata:
    row = area.area
    level: AdministrativeLevel = row.area_type
    if row.area_type == "region":
        level = next(
            (
                level
                for country, number, level in _LEGACY_REGION_LEVELS
                if row.osm_admin_level == number
                and (country is None or country == row.country_code)
            ),
            "region",
        )
    country = AdministrativeIdentity("country", row.country_code, row.country_code, "ISO-3166-1")
    # Reuse the existing authoritative catalog mapping in this adapter only.
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
    return AdministrativeMetadata(level, row.country_code, code, system, parent, ancestors)
