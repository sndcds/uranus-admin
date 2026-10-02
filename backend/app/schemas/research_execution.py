"""Closed execution results and internal filters; never accepted from a browser."""

from datetime import date, time
from typing import Annotated, Literal

from pydantic import Field

from app.schemas.genre import GenreKey
from app.schemas.research import (
    ResearchFilters,
    ResearchRecord,
    SemanticResearchFilters,
    SemanticResearchRecord,
)
from app.schemas.research_location import Place, PlaceFilter
from app.schemas.research_values import ClosedModel, Slot

ExecutionMetric = Literal["event_count", "occurrence_count", "venue_count", "organization_count"]
ExecutionGrouping = Literal[
    "event",
    "venue",
    "organization",
    "category",
    "genre",
    "event_type",
    "municipality",
    "district",
    "state",
    "country",
    "region",
]
TaxonomyKind = Literal["genre", "event_type", "category"]


class ExecutionFilters(ResearchFilters):
    place: PlaceFilter | None = Field(default=None, exclude=True)
    time_from: time | None = None
    time_of_day: Literal["none", "morning", "afternoon", "evening", "night"] = "none"
    area_relation: Literal["inside", "outside"] = "inside"
    event_type_ids: list[int] = Field(default_factory=list, max_length=8)
    category_ids: list[int] = Field(default_factory=list, max_length=8)
    genre_keys: list[GenreKey] = Field(default_factory=list, max_length=8)


class ExecutionSemanticFilters(SemanticResearchFilters):
    place: PlaceFilter | None = Field(default=None, exclude=True)
    # Topic and optional focus are each <=500, joined by one newline.
    # The classic endpoint remains 2–120.
    q: str = Field(min_length=1, max_length=1001)
    time_from: time | None = None
    time_of_day: Literal["none", "morning", "afternoon", "evening", "night"] = "none"
    area_relation: Literal["inside", "outside"] = "inside"
    event_type_ids: list[int] = Field(default_factory=list, max_length=8)
    category_ids: list[int] = Field(default_factory=list, max_length=8)


class ResolutionCandidate(ClosedModel):
    entity_type: Literal[
        "area", "venue", "organization", "category", "event_type", "genre", "place"
    ]
    id: str
    label: str
    place: Place | None = None


ResolutionField = Literal[
    "place_query",
    "location_context",
    "area_query",
    "venue_query",
    "organization_query",
    "event_type_queries",
    "category_queries",
    "genre_queries",
    "comparison_targets",
]


class ResolvedField(ClosedModel):
    field: ResolutionField
    query: Slot
    target: ResolutionCandidate


class ExecutionClarification(ClosedModel):
    kind: Literal["needs_clarification"] = "needs_clarification"
    reason: Literal["planner", "ambiguous", "no_match", "duplicate_target", "taxonomy_conflict"]
    planner_state: Literal["none", "needs_criteria", "needs_location", "needs_date"] = "none"
    field: ResolutionField | None = None
    query: Slot | None = None
    candidates: list[ResolutionCandidate] = Field(default_factory=list, max_length=5)


class RecordsResult(ClosedModel):
    kind: Literal["records"] = "records"
    items: list[SemanticResearchRecord | ResearchRecord] = Field(max_length=20)
    # Exact total only for structured selections; semantic retrieval is top-K.
    total: int | None = Field(default=None, ge=0)


class CountResult(ClosedModel):
    kind: Literal["count"] = "count"
    metric: ExecutionMetric
    value: int = Field(ge=0)


class AggregateItem(ClosedModel):
    key: str
    name: str
    value: int = Field(ge=0)


class AggregateResult(ClosedModel):
    kind: Literal["aggregate"] = "aggregate"
    metric: ExecutionMetric
    group_by: ExecutionGrouping
    items: list[AggregateItem] = Field(max_length=20)


class ComparisonItem(ClosedModel):
    target: ResolutionCandidate
    value: int = Field(ge=0)


class ComparisonResult(ClosedModel):
    kind: Literal["comparison"] = "comparison"
    metric: ExecutionMetric
    items: list[ComparisonItem] = Field(min_length=2, max_length=4)


class TaxonomyItem(ClosedModel):
    key: str
    name: str
    event_count: int = Field(ge=0)


class TaxonomyResult(ClosedModel):
    kind: Literal["taxonomy"] = "taxonomy"
    taxonomy: TaxonomyKind
    items: list[TaxonomyItem] = Field(max_length=20)
    total: int = Field(ge=0)


class SpatialResult(ClosedModel):
    kind: Literal["spatial"] = "spatial"
    spatial_metric: Literal["longitude", "latitude"]
    ordering: Literal["asc", "desc"]
    items: list[ResearchRecord] = Field(max_length=20)


ExecutionResult = Annotated[
    RecordsResult
    | CountResult
    | AggregateResult
    | ComparisonResult
    | ExecutionClarification
    | TaxonomyResult
    | SpatialResult,
    Field(discriminator="kind"),
]


class ExecutionProvenance(ClosedModel):
    structured: bool = False
    semantic: bool = False
    from_date: date | None = None
    to_date: date | None = None
    time_from: time | None = None
    time_of_day: Literal["none", "morning", "afternoon", "evening", "night"] = "none"
    area_relation: Literal["inside", "outside"] = "inside"
    event_type_ids: list[int] = Field(default_factory=list, max_length=8)
    category_ids: list[int] = Field(default_factory=list, max_length=8)
    genre_keys: list[GenreKey] = Field(default_factory=list, max_length=8)


class ExecutionDiagnostics(ClosedModel):
    planner_ms: float = Field(ge=0)
    resolution_ms: float = Field(default=0, ge=0)
    execution_ms: float = Field(default=0, ge=0)
    total_ms: float = Field(ge=0)
    returned_count: int = Field(default=0, ge=0, le=20)
