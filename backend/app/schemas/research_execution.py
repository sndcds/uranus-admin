"""Closed execution results and internal filters; never accepted from a browser."""

from datetime import date, datetime, time
from typing import Annotated, Literal

from pydantic import Field

from app.schemas.genre import GenreKey
from app.schemas.research import (
    ResearchFilters,
    ResearchRecord,
    SemanticResearchFilters,
    SemanticResearchRecord,
)
from app.schemas.research_planner import ClosedModel, PlanResponse, Query, Slot

ExecutionMetric = Literal["event_count", "occurrence_count", "venue_count", "organization_count"]
ExecutionGrouping = Literal["venue", "organization", "category"]


class ExecutionFilters(ResearchFilters):
    time_from: time | None = None
    category_ids: list[int] = Field(default_factory=list, max_length=8)
    genre_keys: list[GenreKey] = Field(default_factory=list, max_length=8)


class ExecutionSemanticFilters(SemanticResearchFilters):
    # Topic and optional focus are each <=500, joined by one newline.
    # The classic endpoint remains 2–120.
    q: str = Field(min_length=1, max_length=1001)
    time_from: time | None = None
    category_ids: list[int] = Field(default_factory=list, max_length=8)


class ResolutionCandidate(ClosedModel):
    entity_type: Literal["area", "venue", "organization", "category", "genre"]
    id: str
    label: str


ResolutionField = Literal[
    "area_query",
    "venue_query",
    "organization_query",
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
    reason: Literal["planner", "ambiguous", "no_match", "duplicate_target"]
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


ExecutionResult = Annotated[
    RecordsResult | CountResult | AggregateResult | ComparisonResult | ExecutionClarification,
    Field(discriminator="kind"),
]


class ExecutionProvenance(ClosedModel):
    structured: bool = False
    semantic: bool = False
    from_date: date | None = None
    to_date: date | None = None
    time_from: time | None = None
    category_ids: list[int] = Field(default_factory=list, max_length=8)
    genre_keys: list[GenreKey] = Field(default_factory=list, max_length=8)


class ExecutionDiagnostics(ClosedModel):
    planner_ms: float = Field(ge=0)
    resolution_ms: float = Field(default=0, ge=0)
    execution_ms: float = Field(default=0, ge=0)
    total_ms: float = Field(ge=0)
    returned_count: int = Field(default=0, ge=0, le=20)


class ResearchExecutionResponse(ClosedModel):
    query: Query
    plan: PlanResponse
    resolution: list[ResolvedField] = Field(default_factory=list, max_length=23)
    result: ExecutionResult
    execution: ExecutionProvenance
    observed_at: datetime
    timezone: str
    diagnostics: ExecutionDiagnostics
