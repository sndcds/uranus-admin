"""Explicit, atomic operator import of reviewed district/state boundaries.

No discovery, deployment hook, source writes or municipality reclassification.
The Geocoder owns level classification; reviewed manifest metadata supplies only
storage fields which its current wire contract does not expose.
"""

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Self
from uuid import uuid4

from pydantic import Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.auth.diagnostics import operator_boundary, operator_engine
from app.clients.research_geocoder import ResearchGeocoderClient
from app.config import Settings
from app.research.administrative_catalog import MAX_CATALOG_BYTES
from app.research.administrative_import import Manifest
from app.research.administrative_resolver import resolved_boundary
from app.research.areas import IMPORT_GRANTS, IMPORT_LOCK, REGIONS
from app.services.nominatim import validate_geometry
from app.storage_preflight import check_grants, check_schema


class PersistentManifest(Manifest):
    """One reviewed level/region per batch; never infer these fields from names."""

    region_code: str = Field(min_length=5, max_length=5)
    osm_admin_level: int = Field(ge=2, le=12)

    @model_validator(mode="after")
    def persistent_scope(self) -> Self:
        if self.level not in {"district", "state"}:
            raise ValueError("Persistent import supports district and state only")
        if self.region_code not in REGIONS or self.country_codes not in (
            [self.region_code[:2]],
            [self.region_code[:2].lower()],
        ):
            raise ValueError("Select exactly the reviewed region's country")
        if not 1 <= len(self.identities) <= 100 or any(
            i.osm_type != "R" or i.osm_id > 2**63 - 1 for i in self.identities
        ):
            raise ValueError("Select 1–100 unique positive bigint relation identities")
        return self


@dataclass(frozen=True)
class Boundary:
    osm_id: int
    area_type: str
    country_code: str
    region_code: str
    name: str
    display_name: str
    osm_admin_level: int
    geometry: str


async def boundaries(
    client: ResearchGeocoderClient, manifest: PersistentManifest
) -> list[Boundary]:
    result = []
    size = 0
    for identity in manifest.identities:
        place = await client.administrative_boundary(identity.osm_type, identity.osm_id)
        if place is None:
            raise ValueError("Boundary missing")
        resolved = resolved_boundary(place, manifest.level)
        if (
            place.osm_type != "relation"
            or place.osm_id != identity.osm_id
            or "municipality" in place.administrative_levels
            or place.administrative_level == "municipality"
            or resolved.country_code != manifest.region_code[:2]
            or place.boundary is None
        ):
            raise ValueError("Boundary identity/country mismatch or municipality role")
        if (
            manifest.level == "state"
            and resolved.code_system == "ISO-3166-2"
            and resolved.official_code != manifest.region_code
        ):
            raise ValueError("State code mismatch")
        name, display = resolved.name, place.display_name
        if (
            not name.strip()
            or len(name) > 240
            or not display
            or not display.strip()
            or len(display) > 1024
        ):
            raise ValueError("Boundary name exceeds storage bounds")
        geometry = validate_geometry(place.boundary.model_dump(mode="json"), 500_000)
        size += len(geometry.encode())
        if size > MAX_CATALOG_BYTES:
            raise ValueError("Boundary batch exceeds byte limit")
        result.append(
            Boundary(
                identity.osm_id,
                manifest.level,
                resolved.country_code,
                manifest.region_code,
                name,
                display,
                manifest.osm_admin_level,
                geometry,
            )
        )
    return result


async def classify(connection: AsyncConnection, item: Boundary) -> str:
    params = asdict(item)
    # Validate topology separately: never run overlap/equality on invalid polygons.
    valid = await connection.scalar(
        text("""WITH candidate AS (
        SELECT ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326) g
    ) SELECT ST_IsValid(g) AND NOT ST_IsEmpty(g) AND ST_NPoints(g)<=500000
      FROM candidate"""),
        params,
    )
    if not valid:
        raise ValueError("Invalid boundary geometry")
    row = (
        (
            await connection.execute(
                text("""SELECT area_type,
        name=:name AND display_name=:display_name AND country_code=:country_code
        AND region_code=:region_code AND osm_admin_level=:osm_admin_level
        AND municipality_key IS NULL AND population_count IS NULL
        AND population_date IS NULL AND population_source IS NULL
        AND population_name IS NULL AND population_file_sha256 IS NULL
        AND population_imported_at IS NULL
        AND ST_Equals(geometry,ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326)) unchanged
        FROM admin.research_area WHERE osm_type='R' AND osm_id=:osm_id"""),
                params,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return "new"
    if row["area_type"] != item.area_type:
        raise ValueError("Existing OSM identity has a conflicting area_type")
    return "unchanged" if row["unchanged"] else "updated"


async def validate_overlaps(connection: AsyncConnection, items: list[Boundary]) -> None:
    # Compare final batch geometries with each other and with same-level stored
    # rows not replaced by this batch. Hierarchical containment is intentional.
    overlap = await connection.scalar(
        text("""WITH incoming AS MATERIALIZED (
        SELECT osm_id,area_type,ST_SetSRID(ST_GeomFromGeoJSON(geometry),4326) g
        FROM jsonb_to_recordset(CAST(:items AS jsonb))
            AS x(osm_id bigint,area_type text,geometry text)
    ) SELECT EXISTS (
        SELECT 1 FROM incoming i JOIN incoming j ON i.osm_id<j.osm_id
        AND i.area_type=j.area_type AND i.g && j.g AND ST_Relate(i.g,j.g,'2********')
    ) OR EXISTS (
        SELECT 1 FROM incoming i JOIN admin.research_area a
        ON a.area_type=i.area_type AND a.geometry && i.g
        WHERE NOT EXISTS (SELECT 1 FROM incoming j WHERE a.osm_type='R' AND j.osm_id=a.osm_id)
        AND ST_Relate(a.geometry,i.g,'2********')
    )"""),
        {"items": json.dumps([asdict(i) for i in items])},
    )
    if overlap:
        raise ValueError("Same-level boundaries overlap in positive area")


async def persist(connection: AsyncConnection, item: Boundary, status: str) -> None:
    params = {**asdict(item), "id": uuid4()}
    if status == "unchanged":
        await connection.execute(
            text("""UPDATE admin.research_area SET retrieved_at=now()
            WHERE osm_type='R' AND osm_id=:osm_id AND area_type=:area_type"""),
            params,
        )
        return
    written = await connection.scalar(
        text("""WITH candidate AS (
        SELECT ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326)) g
    ) INSERT INTO admin.research_area
        (id,area_type,country_code,region_code,name,display_name,osm_type,osm_id,osm_admin_level,
         geometry,centroid,source,retrieved_at,created_at,updated_at)
        SELECT :id,:area_type,:country_code,:region_code,:name,:display_name,'R',:osm_id,
        :osm_admin_level,g,ST_PointOnSurface(g),'osm',now(),now(),now() FROM candidate
        ON CONFLICT (osm_type,osm_id) DO UPDATE SET
        name=EXCLUDED.name,display_name=EXCLUDED.display_name,
        country_code=EXCLUDED.country_code,region_code=EXCLUDED.region_code,
        osm_admin_level=EXCLUDED.osm_admin_level,geometry=EXCLUDED.geometry,
        centroid=EXCLUDED.centroid,source=EXCLUDED.source,retrieved_at=EXCLUDED.retrieved_at,
        updated_at=EXCLUDED.updated_at,municipality_key=NULL,
        population_count=NULL,population_date=NULL,population_source=NULL,
        population_name=NULL,population_file_sha256=NULL,population_imported_at=NULL
        WHERE research_area.area_type=EXCLUDED.area_type RETURNING id"""),
        params,
    )
    if written is None:
        raise ValueError("Existing OSM identity has a conflicting area_type")


async def import_areas(
    connection: AsyncConnection,
    client: ResearchGeocoderClient,
    manifest: PersistentManifest,
    *,
    apply: bool = False,
) -> dict[str, object]:
    items = await boundaries(client, manifest)  # No network during the DB transaction.
    async with connection.begin():
        if not apply:
            await connection.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
        await connection.execute(text("SET LOCAL statement_timeout='10s'"))
        await connection.execute(text("SET LOCAL lock_timeout='10s'"))
        await connection.execute(text("SET LOCAL TIME ZONE 'UTC'"))
        await connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": IMPORT_LOCK})
        if apply:
            # Serialize even writers not using the importer advisory lock. Reads remain available.
            await connection.execute(
                text("LOCK TABLE admin.research_area IN SHARE ROW EXCLUSIVE MODE")
            )
        statuses = [await classify(connection, item) for item in items]
        await validate_overlaps(connection, items)
        if apply:
            for item, status in zip(items, statuses, strict=True):
                await persist(connection, item, status)
    return {
        "mode": "apply" if apply else "plan",
        "counts": {s: statuses.count(s) for s in ("new", "updated", "unchanged")},
        "items": [
            {
                "osm_type": "R",
                "osm_id": i.osm_id,
                "name": i.name,
                "area_type": i.area_type,
                "status": s,
            }
            for i, s in zip(items, statuses, strict=True)
        ],
    }


async def run(
    settings: Settings, manifest: PersistentManifest, *, apply: bool
) -> dict[str, object]:
    engine = operator_engine(settings)
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                await operator_boundary(connection)
                await check_schema(connection)
                await check_grants(connection, IMPORT_GRANTS)
            client = ResearchGeocoderClient(settings)
            try:
                return await import_areas(connection, client, manifest, apply=apply)
            finally:
                await client.close()
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["plan", "apply"])
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        with args.manifest.open("rb") as handle:
            raw = handle.read(64 * 1024 + 1)
        if len(raw) > 64 * 1024:
            raise ValueError("Manifest exceeds byte limit")
        manifest = PersistentManifest.model_validate_json(raw)
        settings = Settings(_env_file=None)  # type: ignore[call-arg]
        report = asyncio.run(run(settings, manifest, apply=args.mode == "apply"))
        print(json.dumps(report, ensure_ascii=False))
    except Exception:
        # Provider/driver/validation details can contain secrets or geometry.
        raise SystemExit(
            "Administrative area import failed; no batch applied. Check manifest, "
            "geocoder metadata/boundaries, conflicts, migration and operator grants."
        ) from None


if __name__ == "__main__":
    main()
