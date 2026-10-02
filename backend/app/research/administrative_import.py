"""Build a reviewed inventory through the private Geocoder; never infer completeness.

python -m app.research.administrative_import manifest.json output.json
The manifest is an operator-supplied authoritative list, not search results.
No production service or database is changed by this command.
"""

import argparse
import asyncio
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from app.clients.research_geocoder import ResearchGeocoderClient
from app.config import Settings
from app.research.administrative_catalog import MAX_CATALOG_BYTES, Catalog, Catalogs
from app.research.administrative_resolver import resolved_boundary
from app.research.internal_plan import AdministrativeLevel
from app.schemas.research_planner import ClosedModel


class Identity(ClosedModel):
    osm_type: Literal["N", "W", "R"]
    osm_id: int = Field(gt=0)


class Manifest(ClosedModel):
    level: AdministrativeLevel
    parent_area_id: str | None
    country_codes: list[str] = Field(min_length=1, max_length=250)
    inventory_source: str = Field(min_length=1, max_length=500)
    complete: bool
    identities: list[Identity] = Field(max_length=12000)

    @model_validator(mode="after")
    def unique_identities(self) -> Self:
        if len({(i.osm_type, i.osm_id) for i in self.identities}) != len(self.identities):
            raise ValueError("Duplicate manifest identity")
        return self


async def build(client: ResearchGeocoderClient, manifest: Manifest) -> Catalog:
    items = []
    size = 0
    for identity in manifest.identities:
        candidate = await client.administrative_boundary(identity.osm_type, identity.osm_id)
        if candidate is None:
            raise ValueError("Inventory boundary missing")
        resolved_boundary(candidate, manifest.level)
        size += len(candidate.model_dump_json().encode())
        if size > MAX_CATALOG_BYTES:
            raise ValueError("Inventory exceeds byte limit")
        items.append(candidate)
    return Catalog(
        schema_version="administrative-catalog-v1",
        level=manifest.level,
        parent_area_id=manifest.parent_area_id,
        country_codes=manifest.country_codes,
        complete=manifest.complete,
        inventory_source=manifest.inventory_source,
        items=items,
    )


async def run(manifest: Manifest) -> Catalog:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    client = ResearchGeocoderClient(settings)
    try:
        return await build(client, manifest)
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        with args.manifest.open("rb") as handle:
            raw = handle.read(MAX_CATALOG_BYTES + 1)
        if len(raw) > MAX_CATALOG_BYTES:
            raise ValueError("Manifest exceeds byte limit")
        catalog = asyncio.run(run(Manifest.model_validate_json(raw)))
        serialized = Catalogs(catalogs=[catalog]).model_dump_json(indent=2).encode()
        if len(serialized) > MAX_CATALOG_BYTES:
            raise ValueError("Inventory exceeds byte limit")
        # Exclusive creation leaves existing Library/operator artifacts untouched.
        with args.output.open("xb") as handle:
            handle.write(serialized)
    except Exception:
        raise SystemExit(
            "Inventory build failed; check manifest, geocoder and output path."
        ) from None


if __name__ == "__main__":
    main()
