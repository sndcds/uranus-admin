"""Explicit operator import of OSM municipalities through the configured Nominatim.

Plan and apply use the same bounded pipeline. Normal Research queries never call it.
"""

import argparse
import asyncio
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth.diagnostics import operator_boundary, operator_engine
from app.config import Settings
from app.errors import APIError
from app.logging import configure_logging
from app.research.catalog import CatalogEntry, load_catalog
from app.schemas.geo import GeoAreaSearchItem
from app.services.nominatim import NominatimClient, area_item, validate_geometry
from app.storage_preflight import check_grants, check_schema

logger = logging.getLogger("admin.research_areas")
MUNICIPALITY_LEVELS = {"DE": 8, "DK": 7}
REGIONS = {
    "DE-SH": "Schleswig-Holstein",
    "DE-HH": "Hamburg",
    "DE-MV": "Mecklenburg-Vorpommern",
    "DE-NI": "Niedersachsen",
    "DE-HB": "Bremen",
    "DK-83": "Region Syddanmark",
}
# Individually verified against the self-hosted provider, 2026-09-27.
# Relation, actual level and official municipality key must ALL match.
CITY_EXCEPTIONS = {
    27020: ("DE-SH", 6, "01001000"),  # Flensburg
    27021: ("DE-SH", 6, "01002000"),  # Kiel
    62782: ("DE-HH", 4, "02000000"),  # Hamburg, both Land and municipality
    62559: ("DE-HB", 6, "04011000"),  # Bremen city, never the two-city Land R62718
    62658: ("DE-HB", 6, "04012000"),  # Bremerhaven
    27027: ("DE-SH", 6, "01003000"),  # Lübeck
    62528: ("DE-SH", 6, "01004000"),  # Neumünster
    62531: ("DE-NI", 6, "03101000"),  # Braunschweig
    62659: ("DE-NI", 6, "03102000"),  # Salzgitter
    62418: ("DE-NI", 6, "03103000"),  # Wolfsburg
    62414: ("DE-NI", 6, "03401000"),  # Delmenhorst
    62562: ("DE-NI", 6, "03402000"),  # Emden
    62409: ("DE-NI", 6, "03403000"),  # Oldenburg (Oldb)
    62631: ("DE-NI", 6, "03404000"),  # Osnabrück
    62444: ("DE-NI", 6, "03405000"),  # Wilhelmshaven
    62405: ("DE-MV", 6, "13003000"),  # Rostock
    62685: ("DE-MV", 6, "13004000"),  # Schwerin
}
IMPORT_GRANTS = {"alembic_version": ("SELECT",), "research_area": ("SELECT", "INSERT", "UPDATE")}
IMPORT_LOCK = 72619334016


@dataclass(frozen=True)
class Boundary:
    osm_id: int
    country_code: str
    region_code: str
    name: str
    display_name: str
    osm_admin_level: int
    geometry: str
    municipality_key: str | None


def municipality_item(
    row: dict[str, Any], region: str, expected_ags: str | None = None
) -> GeoAreaSearchItem | None:
    item = area_item(row)
    address = row.get("address") or {}
    tags = row.get("extratags") or {}
    if item is None or not isinstance(address, dict) or not isinstance(tags, dict):
        return None
    country = (item.country_code or "").upper()
    level = item.admin_level
    osm_id = int(item.osm_id)
    exception = CITY_EXCEPTIONS.get(osm_id)
    if (
        (expected_ags is not None and tags.get("de:amtlicher_gemeindeschluessel") != expected_ags)
        or region not in REGIONS
        or not 0 < osm_id < 2**63
        or address.get("ISO3166-2-lvl4") != region
        or country != region[:2]
        or country not in MUNICIPALITY_LEVELS
        or (
            level != MUNICIPALITY_LEVELS[country]
            and not (
                country == "DE"
                and exception is not None
                and exception == (region, level, tags.get("de:amtlicher_gemeindeschluessel"))
            )
        )
    ):
        return None
    return item


def boundary(
    row: dict[str, Any], settings: Settings, region: str, expected_ags: str | None = None
) -> Boundary:
    item = municipality_item(row, region, expected_ags)
    if item is None:
        raise APIError(422, "research_area_ineligible", "Not an eligible municipality.")
    country = (item.country_code or "").upper()
    tags = row.get("extratags") or {}
    assert item.admin_level is not None
    return Boundary(
        int(item.osm_id),
        country,
        region,
        item.name,
        item.display_name,
        item.admin_level,
        validate_geometry(row.get("geojson"), settings.nominatim_max_geometry_points),
        tags.get("de:amtlicher_gemeindeschluessel")
        if country == "DE"
        and re.fullmatch(r"[0-9]{8}", str(tags.get("de:amtlicher_gemeindeschluessel", "")))
        else None,
    )


def provider_policy(settings: Settings) -> None:
    # Reuse the existing setting and transport, with no public service fallback.
    if settings.nominatim_base_url != "https://nominatim.oklabflensburg.de" and not (
        settings.app_env in {"development", "test"}
        and settings.nominatim_base_url in {"http://127.0.0.1:8080", "https://provider.test"}
    ):
        raise APIError(
            503, "geo_provider_unavailable", "Configure the self-hosted Nominatim origin."
        )


async def discover(
    provider: NominatimClient, region: str, queries: list[str], identities: list[int]
) -> tuple[list[int], int]:
    found = set(identities)
    rejected = 0
    for query in queries:
        rows = await provider.discover_boundaries(query, region[:2].lower())
        for row in rows:
            item = area_item(row)
            if item is None:
                rejected += 1
            else:
                found.add(int(item.osm_id))
        await asyncio.sleep(provider.settings.geocode_request_interval_ms / 1000)
    # Nominatim ranks results; discovery is NEVER an exhaustive municipal inventory.
    if len(found) > 100:
        raise APIError(422, "research_area_import_limit", "Use at most 100 relations per import.")
    return sorted(found), rejected


async def classify(connection: AsyncConnection, item: Boundary) -> tuple[str, dict[str, Any]]:
    params = {**vars(item), "id": uuid4()}
    row = (
        (
            await connection.execute(
                text("""WITH candidate AS MATERIALIZED (
        SELECT ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326)) g
    ) SELECT ST_IsValid(g) AND NOT ST_IsEmpty(g) valid,
        EXISTS(SELECT 1 FROM admin.research_area a WHERE a.osm_type='R' AND a.osm_id=:osm_id)
        existing,
        EXISTS(SELECT 1 FROM admin.research_area a WHERE a.osm_type='R' AND a.osm_id=:osm_id
            AND a.name=:name AND a.display_name=:display_name AND a.country_code=:country_code
            AND a.region_code=:region_code AND a.osm_admin_level=:osm_admin_level
            AND a.municipality_key IS NOT DISTINCT FROM :municipality_key
            AND a.area_type='municipality' AND ST_Equals(a.geometry,g)) unchanged,
        EXISTS(SELECT 1 FROM admin.research_area a WHERE a.osm_id<>:osm_id
            AND a.area_type='municipality' AND a.geometry && g
            AND ST_Relate(a.geometry,g,'2********')) overlap
        FROM candidate"""),
                params,
            )
        )
        .mappings()
        .one()
    )
    # Shared edges/points are legitimate; positive-area overlaps are ambiguous.
    if not row["valid"] or row["overlap"]:
        return "rejected", params
    return ("unchanged" if row["unchanged"] else "updated" if row["existing"] else "new"), params


async def persist(connection: AsyncConnection, params: dict[str, Any], status: str) -> None:
    if status == "unchanged":
        await connection.execute(
            text(
                "UPDATE admin.research_area SET retrieved_at=now() "
                "WHERE osm_type='R' AND osm_id=:osm_id"
            ),
            params,
        )
        return
    await connection.execute(
        text("""WITH candidate AS (
        SELECT ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326)) g
    ) INSERT INTO admin.research_area
        (id,area_type,country_code,region_code,name,display_name,osm_type,osm_id,osm_admin_level,
        geometry,centroid,source,retrieved_at,created_at,updated_at,municipality_key)
        SELECT :id,'municipality',:country_code,:region_code,:name,:display_name,'R',:osm_id,
        :osm_admin_level,g,ST_PointOnSurface(g),'osm',now(),now(),now(),:municipality_key
        FROM candidate
        ON CONFLICT (osm_type,osm_id) DO UPDATE SET area_type=EXCLUDED.area_type,name=EXCLUDED.name,
        display_name=EXCLUDED.display_name,country_code=EXCLUDED.country_code,
        region_code=EXCLUDED.region_code,osm_admin_level=EXCLUDED.osm_admin_level,
        geometry=EXCLUDED.geometry,centroid=EXCLUDED.centroid,retrieved_at=EXCLUDED.retrieved_at,
        population_count=CASE WHEN research_area.municipality_key=EXCLUDED.municipality_key 
            THEN research_area.population_count ELSE NULL END,
        population_date=CASE WHEN research_area.municipality_key=EXCLUDED.municipality_key 
            THEN research_area.population_date ELSE NULL END,
        population_source=CASE WHEN research_area.municipality_key=EXCLUDED.municipality_key 
            THEN research_area.population_source ELSE NULL END,
        population_name=CASE WHEN research_area.municipality_key=EXCLUDED.municipality_key 
            THEN research_area.population_name ELSE NULL END,
        population_file_sha256=CASE WHEN research_area.municipality_key=EXCLUDED.municipality_key 
            THEN research_area.population_file_sha256 ELSE NULL END,
        population_imported_at=CASE WHEN research_area.municipality_key=EXCLUDED.municipality_key 
            THEN research_area.population_imported_at ELSE NULL END,
        municipality_key=EXCLUDED.municipality_key,
        updated_at=EXCLUDED.updated_at"""),
        params,
    )


async def import_boundaries(
    connection: AsyncConnection,
    provider: NominatimClient,
    region: str,
    queries: list[str],
    identities: list[int],
    *,
    apply: bool = False,
    catalog: list[CatalogEntry] | None = None,
) -> dict[str, int]:
    provider_policy(provider.settings)
    if (
        region not in REGIONS
        or len(queries) + len(identities) + len(catalog or []) > 100
        or not (queries or identities or catalog)
    ):
        raise APIError(422, "invalid_input", "Select a region and 1–100 queries or relation IDs.")
    counts = dict.fromkeys(("found", "new", "updated", "unchanged", "rejected"), 0)
    logger.info("research_area_import_started", extra={"region": region, "apply": apply})
    found, counts["rejected"] = await discover(provider, region, queries, identities)
    expected: dict[int, str] = {}
    for entry in catalog or []:
        if entry.region_code != region:
            raise APIError(422, "invalid_input", "Catalog region does not match.")
        # These identities were individually verified; lookup still checks the
        # AGS, hierarchy and geometry. Repeating city/state names can confuse search.
        candidates = {
            identity
            for identity, (scope, _, ags) in CITY_EXCEPTIONS.items()
            if scope == region and ags == entry.ags
        }
        if not candidates:
            for query in (f"{entry.name}, {REGIONS[region]}, Deutschland", entry.name):
                rows = await provider.discover_boundaries(query, "de")
                candidates = {
                    int(candidate.osm_id)
                    for row in rows
                    if (candidate := municipality_item(row, region, entry.ags)) is not None
                }
                await asyncio.sleep(provider.settings.geocode_request_interval_ms / 1000)
                if candidates:
                    break
        if len(candidates) != 1:
            counts["rejected"] += 1
        else:
            identity = candidates.pop()
            found.append(identity)
            expected[identity] = entry.ags
    found = sorted(set(found))
    if len(found) > 100:
        raise APIError(422, "research_area_import_limit", "Use at most 100 relations per import.")
    counts["found"] = len(found) + counts["rejected"]
    items = []
    size = 0
    # Fetch the complete bounded batch before mutation. Provider outages cannot
    # publish a partial import or remove previously imported boundaries.
    for osm_id in found:
        await asyncio.sleep(provider.settings.geocode_request_interval_ms / 1000)
        try:
            item = boundary(
                await provider.boundary_record(str(osm_id)),
                provider.settings,
                region,
                expected.get(osm_id),
            )
        except APIError as error:
            if error.status != 422:
                raise
            counts["rejected"] += 1
            continue
        size += len(item.geometry.encode())
        if size > provider.settings.nominatim_max_response_bytes:
            raise APIError(
                422, "research_area_import_limit", "Split the import into smaller batches."
            )
        items.append(item)
    async with connection.begin():
        # One transaction and an advisory lock serialize overlapping import jobs.
        await connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": IMPORT_LOCK})
        accepted: list[Boundary] = []
        changes: list[tuple[dict[str, Any], str]] = []
        for item in items:
            status, params = await classify(connection, item)
            if status != "rejected" and accepted:
                # Plan must detect same-batch overlaps without persisting scratch rows.
                overlap = (
                    await connection.execute(
                        text("""SELECT EXISTS (
                    SELECT 1 FROM unnest(CAST(:geometries AS text[])) other(value)
                    WHERE ST_Relate(ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326),
                        ST_SetSRID(ST_GeomFromGeoJSON(value),4326),'2********'))"""),
                        {"geometry": item.geometry, "geometries": [a.geometry for a in accepted]},
                    )
                ).scalar_one()
                if overlap:
                    status = "rejected"
            counts[status] += 1
            if status != "rejected":
                accepted.append(item)
                changes.append((params, status))
        logger.info("research_area_import_plan", extra={"region": region, **counts})
        if apply:
            for params, status in changes:
                await persist(connection, params, status)
    logger.info(
        "research_area_import_completed", extra={"region": region, "apply": apply, **counts}
    )
    return counts


async def run(
    settings: Settings,
    region: str,
    queries: list[str],
    identities: list[int],
    apply: bool,
    catalog: list[CatalogEntry] | None = None,
) -> dict[str, int]:
    provider_policy(settings)
    engine = operator_engine(settings)
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                await connection.execute(text("SET TIME ZONE 'UTC'"))
                await operator_boundary(connection)
                await check_schema(connection)
                await check_grants(connection, IMPORT_GRANTS)
            return await import_boundaries(
                connection,
                NominatimClient(settings),
                region,
                queries,
                identities,
                apply=apply,
                catalog=catalog,
            )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["plan", "apply"])
    parser.add_argument("--region", required=True, choices=sorted(REGIONS))
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--osm-id", action="append", type=int, default=[])
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    if any(not 1 <= len(q.strip()) <= 120 for q in args.query) or any(
        not 0 < i < 2**63 for i in args.osm_id
    ):
        parser.error("Use bounded queries and positive 64-bit OSM relation IDs.")
    try:
        catalog = (
            load_catalog(args.catalog, args.region, args.offset, args.limit)
            if args.catalog
            else None
        )
        settings = Settings()
        configure_logging(settings.log_level)
        counts = asyncio.run(
            run(settings, args.region, args.query, args.osm_id, args.mode == "apply", catalog)
        )
        print(
            json.dumps(
                {"country": args.region[:2], "region": args.region, "mode": args.mode, **counts}
            )
        )
    except KeyboardInterrupt:
        raise SystemExit("Research area import interrupted.") from None
    except Exception:
        raise SystemExit(
            "Research area import failed; check provider, schema and operator grants."
        ) from None


if __name__ == "__main__":
    main()
