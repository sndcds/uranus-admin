"""Operator-built complete inventories; Nominatim search is never an enumeration API."""

import asyncio
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, model_validator

from app.errors import APIError
from app.research.administrative_resolver import resolved_boundary
from app.research.geography import (
    AdministrativeLevel,
    ResolvedAdministrativeAreaRef,
    ResolvedAdministrativeConstraint,
)
from app.schemas.research_administrative import AdministrativePlace
from app.schemas.research_values import ClosedModel

MAX_CATALOG_BYTES = 32 * 1024 * 1024


class Catalog(ClosedModel):
    schema_version: str = Field(pattern=r"^administrative-catalog-v1$")
    level: AdministrativeLevel
    parent_area_id: str | None
    country_codes: list[Annotated[str, Field(pattern=r"^[a-z]{2}$")]] = Field(
        min_length=1, max_length=250
    )
    complete: bool
    inventory_source: str = Field(min_length=1, max_length=500)
    items: list[AdministrativePlace] = Field(max_length=12000)

    @model_validator(mode="after")
    def inventory(self) -> Self:
        if not self.inventory_source.strip():
            raise ValueError("Inventory source required")
        areas = [resolved_boundary(item, self.level) for item in self.items]
        if len({str(area.resolved_id) for area in areas}) != len(areas):
            raise ValueError("Duplicate inventory identity")
        if any(area.country_code.lower() not in self.country_codes for area in areas):
            raise ValueError("Inventory country mismatch")
        return self


class Catalogs(ClosedModel):
    catalogs: list[Catalog] = Field(max_length=100)

    @model_validator(mode="after")
    def total_bound(self) -> Self:
        if sum(len(c.items) for c in self.catalogs) > 12000:
            raise ValueError("Total inventory area limit exceeded")
        return self


def read_catalogs(path: Path) -> Catalogs:
    with path.open("rb") as handle:
        data = handle.read(MAX_CATALOG_BYTES + 1)
    if len(data) > MAX_CATALOG_BYTES:
        raise ValueError("Administrative inventory exceeds byte limit")
    return Catalogs.model_validate_json(data)


async def load_inventory(
    path: Path | None,
    level: AdministrativeLevel,
    spatial: tuple[ResolvedAdministrativeConstraint, ...],
) -> tuple[tuple[ResolvedAdministrativeAreaRef, ...], tuple[str, ...]]:
    if path is None:
        raise APIError(
            422, "research_inventory_unavailable", "A complete area inventory is required."
        )
    try:
        catalogs = await asyncio.to_thread(read_catalogs, path)
    except (OSError, ValueError):
        raise APIError(
            503, "research_inventory_invalid", "The area inventory is unavailable."
        ) from None
    parents = {str(s.reference.resolved_id) for s in spatial if s.relation == "inside"}
    countries = {s.reference.country_code.lower() for s in spatial if s.relation == "inside"}
    available = [c for c in catalogs.catalogs if countries.issubset(c.country_codes)]
    scoped = [
        c for c in available if c.level == level and c.parent_area_id in parents and c.complete
    ]
    choices = scoped or [
        c for c in available if c.level == level and c.parent_area_id is None and c.complete
    ]
    if len(choices) != 1:
        raise APIError(
            422,
            "research_inventory_unavailable",
            "A complete unambiguous area inventory is required.",
        )
    catalog = choices[0]
    return tuple(resolved_boundary(p, level) for p in catalog.items), tuple(catalog.country_codes)
