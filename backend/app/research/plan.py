"""Admin-owned execution intent. Not an HTTP model or a Planner schema mirror."""

from dataclasses import dataclass, field
from datetime import date, time
from typing import Literal

from app.research.geography import (
    AdministrativeLevel,
    ResolvedAdministrativeAreaRef,
    ResolvedAdministrativeConstraint,
    SpatialConstraint,
)
from app.schemas.research_execution import ExecutionFilters, ExecutionGrouping


@dataclass(frozen=True, slots=True)
class NameFilters:
    venue_query: str | None = None
    organization_query: str | None = None
    event_type_queries: tuple[str, ...] = ()
    category_queries: tuple[str, ...] = ()
    genre_queries: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TemporalSelection:
    period: Literal[
        "none",
        "today",
        "tomorrow",
        "this_weekend",
        "next_week",
        "this_month",
        "this_year",
        "past",
        "future",
        "explicit_range",
    ] = "none"
    from_date: date | None = None
    to_date: date | None = None
    time_from: time | None = None
    time_of_day: Literal["none", "morning", "afternoon", "evening", "night"] = "none"


@dataclass(frozen=True, slots=True)
class SemanticSelection:
    query: str
    focus: str | None = None


@dataclass(frozen=True, slots=True)
class ComparisonTarget:
    kind: Literal["venue", "area", "organization"]
    query: str


ResearchIntent = Literal[
    "list",
    "search",
    "recommend",
    "count",
    "aggregate",
    "compare",
    "taxonomy",
    "spatial_rank",
    "rank",
    "relation",
    "trend",
    "anomaly",
    "explain",
    "knowledge",
]


@dataclass(frozen=True, slots=True)
class InternalResearchPlan:
    intent: ResearchIntent
    entity_type: Literal["event", "venue", "organization"]
    metric: Literal[
        "none", "event_count", "occurrence_count", "venue_count", "organization_count"
    ] = "none"
    group_by: Literal[
        "none",
        "event",
        "venue",
        "area",
        "organization",
        "category",
        "genre",
        "event_type",
        "municipality",
        "district",
        "state",
        "country",
        "region",
    ] = "none"
    groupings: tuple[ExecutionGrouping, ...] = ()
    ordering: Literal["asc", "desc"] | None = None
    limit: int | None = None
    filters: NameFilters = field(default_factory=NameFilters)
    temporal: TemporalSelection = field(default_factory=TemporalSelection)
    spatial_constraints: tuple[SpatialConstraint, ...] = ()
    # Request exact coverage diagnostics and polygon/inventory selection. This is
    # an execution capability, independent of the supplying wire version.
    location_coverage: bool = False
    zero_only: bool = False
    spatial_metric: Literal["longitude", "latitude"] | None = None
    semantic: SemanticSelection | None = None
    taxonomy: Literal["genre", "event_type", "category"] | None = None
    comparison_targets: tuple[ComparisonTarget, ...] = ()
    clarification: Literal["none", "needs_criteria", "needs_location", "needs_date"] = "none"
    unsupported_reason: (
        Literal["outside_research", "multi_area", "unsupported_constraint"] | None
    ) = None
    # Closed extension slots, deliberately not speculative v7 constraint models.
    # Their types must be implemented before a future adapter can emit them.
    price: None = None
    relation: None = None
    trend: None = None
    anomaly: None = None
    explain: None = None
    knowledge: None = None

    def __post_init__(self) -> None:
        # Old adapters/constructors retain their scalar entry point. Execution owns
        # the ordered collection; never choose a representative axis of a cube.
        from typing import get_args

        if len(self.groupings) > 3 or len(set(self.groupings)) != len(self.groupings):
            raise ValueError("invalid_grouping_dimensions")
        if any(g not in get_args(ExecutionGrouping) for g in self.groupings):
            raise ValueError("unsupported_grouping_dimension")
        if self.group_by != "none":
            if self.groupings and self.groupings != (self.group_by,):
                raise ValueError("conflicting_grouping_dimensions")
            object.__setattr__(self, "groupings", (self.group_by,))


@dataclass(frozen=True, slots=True)
class ResolvedResearchPlan:
    """Version-independent SQL selection stage; no unresolved names or wire fields."""

    filters: ExecutionFilters
    intent: ResearchIntent
    administrative_constraints: tuple[ResolvedAdministrativeConstraint, ...] = ()
    grouping: AdministrativeLevel | None = None
    zero_only: bool = False
    ordering: Literal["asc", "desc"] = "desc"
    limit: int = 20
    inventory: tuple[ResolvedAdministrativeAreaRef, ...] = ()
    inventory_countries: tuple[str, ...] = ()
