"""Explicit operator import of OSM municipalities through the configured Nominatim.

Plan and apply use the same bounded pipeline. Normal Research queries never call it.
"""

import argparse
import asyncio
import json
import logging
import math
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
from app.research.catalog import REGION_PREFIX, CatalogEntry, load_catalog
from app.research.danish_catalog import DANISH_MUNICIPALITIES
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
    "DE-BB": "Brandenburg",
    "DE-BE": "Berlin",
    "DE-BW": "Baden-Württemberg",
    "DE-BY": "Bayern",
    "DE-HE": "Hessen",
    "DE-NW": "Nordrhein-Westfalen",
    "DE-RP": "Rheinland-Pfalz",
    "DE-SL": "Saarland",
    "DE-SN": "Sachsen",
    "DE-ST": "Sachsen-Anhalt",
    "DE-TH": "Thüringen",
    "DK-81": "Region Nordjylland",
    "DK-82": "Region Midtjylland",
    "DK-83": "Region Syddanmark",
    "DK-84": "Region Hovedstaden",
    "DK-85": "Region Sjælland",
}
# Individually verified against the self-hosted provider, 2026-09-28.
# All 107 BKG city/state municipalities with AGS ending 000 were checked by
# exact AGS, region, country, administrative relation and lookup geometry.
# Relation, actual level and official municipality key must ALL match.
CITY_EXCEPTIONS = {
    27020: ("DE-SH", 6, "01001000"),  # Flensburg
    27021: ("DE-SH", 6, "01002000"),  # Kiel
    27027: ("DE-SH", 6, "01003000"),  # Lübeck
    62528: ("DE-SH", 6, "01004000"),  # Neumünster
    62782: ("DE-HH", 4, "02000000"),  # Hamburg
    62531: ("DE-NI", 6, "03101000"),  # Braunschweig
    62659: ("DE-NI", 6, "03102000"),  # Salzgitter
    62418: ("DE-NI", 6, "03103000"),  # Wolfsburg
    62414: ("DE-NI", 6, "03401000"),  # Delmenhorst
    62562: ("DE-NI", 6, "03402000"),  # Emden
    62409: ("DE-NI", 6, "03403000"),  # Oldenburg (Oldb)
    62631: ("DE-NI", 6, "03404000"),  # Osnabrück
    62444: ("DE-NI", 6, "03405000"),  # Wilhelmshaven
    62559: ("DE-HB", 6, "04011000"),  # Bremen
    62658: ("DE-HB", 6, "04012000"),  # Bremerhaven
    62539: ("DE-NW", 6, "05111000"),  # Düsseldorf
    62456: ("DE-NW", 6, "05112000"),  # Duisburg
    62713: ("DE-NW", 6, "05113000"),  # Essen
    62748: ("DE-NW", 6, "05114000"),  # Krefeld
    62410: ("DE-NW", 6, "05116000"),  # Mönchengladbach
    62385: ("DE-NW", 6, "05117000"),  # Mülheim an der Ruhr
    62734: ("DE-NW", 6, "05119000"),  # Oberhausen
    62455: ("DE-NW", 6, "05120000"),  # Remscheid
    62699: ("DE-NW", 6, "05122000"),  # Solingen
    62478: ("DE-NW", 6, "05124000"),  # Wuppertal
    62508: ("DE-NW", 6, "05314000"),  # Bonn
    62578: ("DE-NW", 6, "05315000"),  # Köln
    62449: ("DE-NW", 6, "05316000"),  # Leverkusen
    62634: ("DE-NW", 6, "05512000"),  # Bottrop
    62522: ("DE-NW", 6, "05513000"),  # Gelsenkirchen
    62591: ("DE-NW", 6, "05515000"),  # Münster
    62646: ("DE-NW", 6, "05711000"),  # Bielefeld
    62644: ("DE-NW", 6, "05911000"),  # Bochum
    1829065: ("DE-NW", 6, "05913000"),  # Dortmund
    1800297: ("DE-NW", 6, "05914000"),  # Hagen
    62499: ("DE-NW", 6, "05915000"),  # Hamm
    62396: ("DE-NW", 6, "05916000"),  # Herne
    62581: ("DE-HE", 6, "06411000"),  # Darmstadt
    62400: ("DE-HE", 6, "06412000"),  # Frankfurt am Main
    62695: ("DE-HE", 6, "06413000"),  # Offenbach am Main
    62496: ("DE-HE", 6, "06414000"),  # Wiesbaden
    535895: ("DE-HE", 6, "06415000"),  # Hanau
    62598: ("DE-HE", 6, "06611000"),  # Kassel
    62512: ("DE-RP", 6, "07111000"),  # Koblenz
    172679: ("DE-RP", 6, "07211000"),  # Trier
    62573: ("DE-RP", 6, "07311000"),  # Frankenthal (Pfalz)
    62652: ("DE-RP", 6, "07312000"),  # Kaiserslautern
    62391: ("DE-RP", 6, "07313000"),  # Landau in der Pfalz
    62347: ("DE-RP", 6, "07314000"),  # Ludwigshafen am Rhein
    62630: ("DE-RP", 6, "07315000"),  # Mainz
    62724: ("DE-RP", 6, "07316000"),  # Neustadt an der Weinstraße
    62642: ("DE-RP", 6, "07317000"),  # Pirmasens
    62352: ("DE-RP", 6, "07318000"),  # Speyer
    62453: ("DE-RP", 6, "07319000"),  # Worms
    62719: ("DE-RP", 6, "07320000"),  # Zweibrücken
    62375: ("DE-BW", 6, "08111000"),  # Stuttgart
    62751: ("DE-BW", 6, "08121000"),  # Heilbronn
    62340: ("DE-BW", 6, "08211000"),  # Baden-Baden
    62518: ("DE-BW", 6, "08212000"),  # Karlsruhe
    62487: ("DE-BW", 6, "08221000"),  # Heidelberg
    62691: ("DE-BW", 6, "08222000"),  # Mannheim
    62471: ("DE-BW", 6, "08231000"),  # Pforzheim
    62768: ("DE-BW", 6, "08311000"),  # Freiburg im Breisgau
    62495: ("DE-BW", 6, "08421000"),  # Ulm
    62381: ("DE-BY", 6, "09161000"),  # Ingolstadt
    62428: ("DE-BY", 6, "09162000"),  # München
    2168233: ("DE-BY", 6, "09163000"),  # Rosenheim
    62484: ("DE-BY", 6, "09261000"),  # Landshut
    62629: ("DE-BY", 6, "09262000"),  # Passau
    62636: ("DE-BY", 6, "09263000"),  # Straubing
    62772: ("DE-BY", 6, "09361000"),  # Amberg
    62411: ("DE-BY", 6, "09362000"),  # Regensburg
    62554: ("DE-BY", 6, "09363000"),  # Weiden i.d.OPf.
    62525: ("DE-BY", 6, "09461000"),  # Bamberg
    62640: ("DE-BY", 6, "09462000"),  # Bayreuth
    62717: ("DE-BY", 6, "09463000"),  # Coburg
    62589: ("DE-BY", 6, "09464000"),  # Hof
    62654: ("DE-BY", 6, "09561000"),  # Ansbach
    62403: ("DE-BY", 6, "09562000"),  # Erlangen
    62374: ("DE-BY", 6, "09563000"),  # Fürth
    62780: ("DE-BY", 6, "09564000"),  # Nürnberg
    62720: ("DE-BY", 6, "09565000"),  # Schwabach
    62532: ("DE-BY", 6, "09661000"),  # Aschaffenburg
    62534: ("DE-BY", 6, "09662000"),  # Schweinfurt
    62464: ("DE-BY", 6, "09663000"),  # Würzburg
    62407: ("DE-BY", 6, "09761000"),  # Augsburg
    62349: ("DE-BY", 6, "09762000"),  # Kaufbeuren
    62701: ("DE-BY", 6, "09763000"),  # Kempten (Allgäu)
    62590: ("DE-BY", 6, "09764000"),  # Memmingen
    62422: ("DE-BE", 4, "11000000"),  # Berlin
    62470: ("DE-BB", 6, "12051000"),  # Brandenburg an der Havel
    62430: ("DE-BB", 6, "12052000"),  # Cottbus
    62523: ("DE-BB", 6, "12053000"),  # Frankfurt (Oder)
    62369: ("DE-BB", 6, "12054000"),  # Potsdam
    62405: ("DE-MV", 6, "13003000"),  # Rostock
    62685: ("DE-MV", 6, "13004000"),  # Schwerin
    62594: ("DE-SN", 6, "14511000"),  # Chemnitz
    191645: ("DE-SN", 6, "14612000"),  # Dresden
    62649: ("DE-SN", 6, "14713000"),  # Leipzig
    62526: ("DE-ST", 6, "15001000"),  # Dessau-Roßlau
    62638: ("DE-ST", 6, "15002000"),  # Halle (Saale)
    62481: ("DE-ST", 6, "15003000"),  # Magdeburg
    62745: ("DE-TH", 6, "16051000"),  # Erfurt
    62671: ("DE-TH", 6, "16052000"),  # Gera
    62693: ("DE-TH", 6, "16053000"),  # Jena
    62450: ("DE-TH", 6, "16054000"),  # Suhl
    62493: ("DE-TH", 6, "16055000"),  # Weimar
}
# Exact-AGS Overpass matches supplied for regular level-8 municipalities whose
# names are unreliable discovery queries. These pin candidates only: every import
# still requires the configured provider's lookup, AGS/hierarchy and geometry checks.
VERIFIED_MUNICIPALITY_RELATIONS = {
    "01057001": 310405,  # Ascheberg (Holstein)
    "01057004": 288915,  # Behrensdorf (Ostsee)
    "01057030": 288939,  # Hohwacht (Ostsee)
    "01061044": 447194,  # Horst (Holstein)
    "03151040": 1392804,  # Wittingen
    "03354026": 1821905,  # Wustrow (Wendland)
    "03357019": 1079013,  # Hamersen
    "03358001": 1808860,  # Ahlden (Aller)
}
DANISH_RELATIONS = {osm_id: region for region, _, _, osm_id in DANISH_MUNICIPALITIES}
IMPORT_GRANTS = {"alembic_version": ("SELECT",), "research_area": ("SELECT", "INSERT", "UPDATE")}
IMPORT_LOCK = 72619334016


@dataclass(frozen=True)
class OverlapLimits:
    max_area_m2: float
    max_percent_each: float


# Operator-verified pairs only; percentages are 0–100, not fractions.
VERIFIED_MUNICIPALITY_OVERLAPS = {
    frozenset({"03151040", "03151007"}): OverlapLimits(60000, 0.10),
    frozenset({"03357019", "03357017"}): OverlapLimits(45000, 0.35),
}


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
        (
            expected_ags is not None
            and (
                not re.fullmatch(r"[0-9]{8}", expected_ags)
                or REGION_PREFIX.get(expected_ags[:2]) != region
                or tags.get("de:amtlicher_gemeindeschluessel") != expected_ags
            )
        )
        or (country == "DK" and DANISH_RELATIONS.get(osm_id) != region)
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
    if not row["valid"]:
        return "rejected", params
    if row["overlap"] and await rejected_overlaps(connection, item):
        return "rejected", params
    return ("unchanged" if row["unchanged"] else "updated" if row["existing"] else "new"), params


async def rejected_overlaps(
    connection: AsyncConnection, item: Boundary, accepted: list[Boundary] | None = None
) -> bool:
    # Fixed application-owned SQL sources; both paths retain the same positive-area
    # predicate. The table path keeps the spatial bounding-box index filter.
    peers = """SELECT osm_id, municipality_key, geometry
        FROM admin.research_area WHERE area_type='municipality'"""
    params: dict[str, Any] = {"geometry": item.geometry, "osm_id": item.osm_id}
    if accepted is not None:
        peers = """SELECT osm_id, municipality_key,
            ST_SetSRID(ST_GeomFromGeoJSON(value),4326) geometry
            FROM unnest(CAST(:osm_ids AS bigint[]), CAST(:keys AS text[]),
                CAST(:geometries AS text[])) p(osm_id, municipality_key, value)"""
        params.update(
            osm_ids=[a.osm_id for a in accepted],
            keys=[a.municipality_key for a in accepted],
            geometries=[a.geometry for a in accepted],
        )
    overlaps = (
        (
            await connection.execute(
                text(f"""WITH candidate AS MATERIALIZED (
                    SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326) g
                ), peers AS ({peers}), measured AS MATERIALIZED (
                    SELECT p.osm_id, p.municipality_key,
                        CASE WHEN ST_IsValid(p.geometry) THEN
                            ST_Area(ST_Intersection(g,p.geometry)::geography) END overlap_m2,
                        ST_Area(g::geography) candidate_m2,
                        CASE WHEN ST_IsValid(p.geometry) THEN
                            ST_Area(p.geometry::geography) END existing_m2
                    FROM candidate CROSS JOIN peers p
                    WHERE p.osm_id<>:osm_id AND p.geometry && g
                        AND ST_Relate(p.geometry,g,'2********')
                ) SELECT osm_id, municipality_key, overlap_m2,
                    100.0 * overlap_m2 / NULLIF(candidate_m2,0) candidate_overlap_percent,
                    100.0 * overlap_m2 / NULLIF(existing_m2,0) existing_overlap_percent
                FROM measured ORDER BY osm_id"""),
                params,
            )
        )
        .mappings()
        .all()
    )
    warnings = []
    for overlap in overlaps:
        existing_ags = overlap["municipality_key"]
        limits = (
            VERIFIED_MUNICIPALITY_OVERLAPS.get(frozenset({item.municipality_key, existing_ags}))
            if item.municipality_key is not None and existing_ags is not None
            else None
        )
        area = overlap["overlap_m2"]
        candidate_percent = overlap["candidate_overlap_percent"]
        existing_percent = overlap["existing_overlap_percent"]
        if (
            limits is None
            or any(
                value is None or not math.isfinite(value) or value <= 0
                for value in (area, candidate_percent, existing_percent)
            )
            or area > limits.max_area_m2
            or candidate_percent > limits.max_percent_each
            or existing_percent > limits.max_percent_each
        ):
            return True
        warnings.append(
            {
                "candidate_ags": item.municipality_key,
                "existing_ags": existing_ags,
                "candidate_osm_id": item.osm_id,
                "existing_osm_id": overlap["osm_id"],
                "overlap_m2": area,
                "candidate_overlap_percent": candidate_percent,
                "existing_overlap_percent": existing_percent,
            }
        )
    for fields in warnings:
        logger.warning("research_area_verified_overlap", extra=fields)
    return False


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
        if (
            entry.region_code != region
            or not re.fullmatch(r"[0-9]{8}", entry.ags)
            or REGION_PREFIX.get(entry.ags[:2]) != region
        ):
            raise APIError(422, "invalid_input", "Catalog region does not match.")
        # These identities were individually verified; lookup still checks the
        # AGS, hierarchy and geometry. Repeating city/state names can confuse search.
        candidates = {
            identity
            for identity, (scope, _, ags) in CITY_EXCEPTIONS.items()
            if scope == region and ags == entry.ags
        }
        if (identity := VERIFIED_MUNICIPALITY_RELATIONS.get(entry.ags)) is not None:
            candidates = {identity}
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
                if await rejected_overlaps(connection, item, accepted):
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
        # Pydantic Settings accepts this runtime option; its synthesized type omits it.
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
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
