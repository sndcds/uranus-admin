"""Execution-neutral Admin algebra, independent of any Planner wire version."""

from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from app.schemas.research_planner import ClosedModel

AdministrativeLevel = Literal["municipality", "district", "state", "country", "region"]
LEVELS: frozenset[str] = frozenset({"municipality", "district", "state", "country", "region"})


class AdministrativeAreaRef(ClosedModel):
    name: str = Field(min_length=1, max_length=300)
    level: AdministrativeLevel
    country_code: str = Field(pattern=r"^[a-z]{2}$")
    official_code: str | None = Field(default=None, max_length=32)
    official_code_type: str | None = Field(default=None, max_length=80)
    osm_type: Literal["N", "W", "R"]
    osm_id: int = Field(gt=0)
    area_id: str = Field(
        pattern=r"^osm:[NWR]:[1-9][0-9]*:(municipality|district|state|country|region)$"
    )
    boundary_reference: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


@dataclass(frozen=True)
class AreaRequest:
    query: str
    expected_level: AdministrativeLevel | None
    country_code: str | None = None


@dataclass(frozen=True)
class SpatialConstraint:
    relation: Literal["inside", "outside"]
    area: AreaRequest


@dataclass(frozen=True)
class InternalResearchPlan:
    operation: Literal["list", "count", "rank", "aggregate"]
    subject: Literal["event", "municipality", "district", "state", "country", "region"]
    grouping: AdministrativeLevel | None
    spatial: tuple[SpatialConstraint, ...]
    category: str | None = None
    metric: Literal["event_count"] = "event_count"
    zero_only: bool = False
    ordering: Literal["asc", "desc"] = "desc"
    limit: int = 20


@dataclass(frozen=True)
class ResolvedBoundary:
    area: AdministrativeAreaRef
    geometry_json: str


@dataclass(frozen=True)
class ResolvedSpatialConstraint:
    relation: Literal["inside", "outside"]
    boundary: ResolvedBoundary


@dataclass(frozen=True)
class ResolvedResearchPlan:
    """No raw geographic or taxonomy query reaches the Executor."""

    operation: Literal["list", "count", "rank", "aggregate"]
    grouping: AdministrativeLevel | None
    spatial: tuple[ResolvedSpatialConstraint, ...]
    category_id: int | None
    zero_only: bool
    ordering: Literal["asc", "desc"]
    limit: int
    inventory: tuple[ResolvedBoundary, ...] = ()
    inventory_countries: tuple[str, ...] = ()
