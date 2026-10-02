"""Closed analytical v5/v10 wire contract; legacy v3/v7 stays frozen."""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


def nonblank(value: str) -> str:
    # Keep grammar-compatible lengths in JSON Schema; validate whitespace here.
    # Return the original text: validation must not silently normalize model output.
    if not value.strip():
        raise ValueError("blank_string")
    return value


Query = Annotated[str, StringConstraints(min_length=1, max_length=2000), AfterValidator(nonblank)]
Slot = Annotated[str, StringConstraints(min_length=1, max_length=160), AfterValidator(nonblank)]
Topic = Annotated[str, StringConstraints(min_length=1, max_length=500), AfterValidator(nonblank)]
EntityType = Literal["event", "venue", "organization"]
Intent = Literal[
    "search", "list", "count", "aggregate", "recommend", "compare", "taxonomy", "spatial_rank"
]
Temporal = Literal[
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
]
Metric = Literal["event_count", "venue_count", "organization_count", "occurrence_count", "none"]
GroupBy = Literal[
    "event", "venue", "area", "organization", "category", "genre", "event_type", "none"
]


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ComparisonTarget(ClosedModel):
    kind: Literal["venue", "area", "organization"]
    query: Slot


class AnalyticalQueryPlan(ClosedModel):
    # Required nullable fields keep native structured output and API schemas identical.
    taxonomy: Literal["genre", "event_type", "category"] | None
    spatial_metric: Literal["longitude", "latitude"] | None
    area_relation: Literal["inside", "outside"]
    original_query: Query
    intent: Intent
    entity_type: EntityType
    semantic_query: Topic | None
    area_query: Slot | None
    venue_query: Slot | None
    organization_query: Slot | None
    event_type_queries: list[Slot] = Field(max_length=8)
    category_queries: list[Slot] = Field(max_length=8)
    genre_queries: list[Slot] = Field(max_length=8)
    temporal: Temporal
    ordering: Literal["asc", "desc"] | None
    limit: Annotated[int, Field(ge=1, le=20)] | None
    explicit_from_date: date | None
    explicit_to_date: date | None
    time_of_day: Literal["none", "morning", "afternoon", "evening", "night"]
    metric: Metric
    group_by: GroupBy
    comparison_targets: list[ComparisonTarget] = Field(max_length=4)
    semantic_focus: Topic | None
    requires_semantic_relevance: bool
    answer_mode: Literal[
        "records", "count", "aggregate", "recommendation", "comparison", "taxonomy"
    ]
    clarification: Literal["none", "needs_criteria", "needs_location", "needs_date"]
    unsupported_reason: Literal["outside_research", "multi_area", "unsupported_constraint"] | None

    @model_validator(mode="after")
    def consistent_plan(self) -> Self:
        if self.unsupported_reason == "outside_research":
            # Out-of-scope input has no research interpretation. Reject residual
            # semantics/filters; never replace model values with these constants.
            neutral: dict[str, object] = {
                "taxonomy": None,
                "spatial_metric": None,
                "area_relation": "inside",
                "intent": "list",
                "entity_type": "event",
                "semantic_query": None,
                "area_query": None,
                "venue_query": None,
                "organization_query": None,
                "event_type_queries": [],
                "category_queries": [],
                "genre_queries": [],
                "temporal": "none",
                "ordering": None,
                "limit": None,
                "explicit_from_date": None,
                "explicit_to_date": None,
                "time_of_day": "none",
                "metric": "none",
                "group_by": "none",
                "comparison_targets": [],
                "semantic_focus": None,
                "requires_semantic_relevance": False,
                "answer_mode": "records",
                "clarification": "none",
            }
            if any(getattr(self, field) != value for field, value in neutral.items()):
                raise ValueError("outside_research_requires_neutral_plan")
        modes = {
            "search": "records",
            "list": "records",
            "count": "count",
            "aggregate": "aggregate",
            "recommend": "recommendation",
            "compare": "comparison",
            "taxonomy": "taxonomy",
            "spatial_rank": "records",
        }
        if self.answer_mode != modes[self.intent]:
            raise ValueError("intent_answer_mode_mismatch")
        if self.limit is not None and self.intent not in {
            "list",
            "search",
            "recommend",
            "aggregate",
            "taxonomy",
            "spatial_rank",
        }:
            raise ValueError("limit_requires_record_results")
        if self.ordering is not None and self.intent not in {
            "aggregate",
            "taxonomy",
            "spatial_rank",
        }:
            if self.intent not in {"list", "search"} or self.answer_mode != "records":
                raise ValueError("ordering_requires_records")
            if self.entity_type != "event":
                raise ValueError("ordering_requires_event")
            if (
                self.semantic_query is not None
                and self.unsupported_reason != "unsupported_constraint"
            ):
                raise ValueError("semantic_ordering_unsupported")
        has_semantics = self.semantic_query is not None
        if self.requires_semantic_relevance != has_semantics:
            raise ValueError("semantic_relevance_mismatch")
        if self.semantic_focus is not None and not has_semantics:
            raise ValueError("semantic_focus_requires_query")
        if self.intent == "search" and not has_semantics:
            raise ValueError("search_requires_semantic_query")
        if self.intent == "recommend" and not has_semantics:
            raise ValueError("recommendation_requires_preference")
        if self.temporal == "explicit_range":
            if self.explicit_from_date is None or self.explicit_to_date is None:
                raise ValueError("explicit_range_requires_both_dates")
            if self.explicit_from_date > self.explicit_to_date:
                raise ValueError("unordered_dates")
        elif self.explicit_from_date is not None or self.explicit_to_date is not None:
            raise ValueError("dates_require_explicit_range")
        if self.intent in {"count", "aggregate"} and self.metric == "none":
            raise ValueError("metric_required")
        if (
            self.intent in {"search", "list", "recommend", "taxonomy", "spatial_rank"}
            and self.metric != "none"
        ):
            raise ValueError("unexpected_metric")
        if self.intent == "aggregate" and self.group_by == "none":
            raise ValueError("grouping_required")
        if self.intent != "aggregate" and self.group_by != "none":
            raise ValueError("unexpected_grouping")
        if self.group_by == "event" and self.metric != "occurrence_count":
            raise ValueError("event_grouping_requires_occurrence_count")
        expected_entity = {
            "event_count": "event",
            "occurrence_count": "event",
            "venue_count": "venue",
            "organization_count": "organization",
        }
        if self.metric != "none" and expected_entity[self.metric] != self.entity_type:
            raise ValueError("metric_entity_mismatch")
        if self.intent != "compare" and self.comparison_targets:
            raise ValueError("unexpected_comparison_targets")
        if self.clarification == "needs_criteria" and self.intent != "compare":
            raise ValueError("criteria_require_comparison")
        if (
            self.intent == "compare"
            and self.clarification == "none"
            and not self.unsupported_reason
        ):
            if len(self.comparison_targets) < 2 or self.metric == "none":
                raise ValueError("comparison_requires_targets_and_metric")
        targets = [(t.kind, t.query.casefold().strip()) for t in self.comparison_targets]
        if len(set(targets)) != len(targets):
            raise ValueError("duplicate_comparison_target")
        if (self.intent == "taxonomy") != (self.taxonomy is not None):
            raise ValueError("taxonomy_intent_required")
        if self.intent == "taxonomy" and self.entity_type != "event":
            raise ValueError("taxonomy_requires_events")
        if (self.intent == "spatial_rank") != (self.spatial_metric is not None):
            raise ValueError("spatial_intent_required")
        if self.intent == "spatial_rank" and (
            self.entity_type not in {"event", "venue"} or self.ordering is None
        ):
            raise ValueError("invalid_spatial_ranking")
        if self.area_relation == "outside" and self.area_query is None:
            raise ValueError("outside_requires_area")
        if (
            self.requires_semantic_relevance
            and self.intent in {"count", "aggregate", "compare", "taxonomy", "spatial_rank"}
            and self.unsupported_reason is None
        ):
            raise ValueError("exact_semantic_analysis_unsupported")
        return self


class AnalyticalDiagnostics(ClosedModel):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    planner_intent: Intent
    planner_model: str = Field(min_length=1, max_length=160)
    planner_prompt_version: Literal["research-planner-v10"]
    planner_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)


class AnalyticalEnvelope(ClosedModel):
    schema_version: Literal["research-query-plan-v5"]
    prompt_version: Literal["research-planner-v10"]
    model: str = Field(min_length=1, max_length=160)
    plan: AnalyticalQueryPlan
    reference_date: date
    timezone: str = Field(max_length=64)
    diagnostics: AnalyticalDiagnostics


class AnalyticalResponse(AnalyticalEnvelope):
    kind: Literal["plan"] = "plan"


class AnalyticalClarification(AnalyticalEnvelope):
    kind: Literal["needs_clarification"] = "needs_clarification"


AnalyticalPlanResponse = Annotated[
    AnalyticalResponse | AnalyticalClarification, Field(discriminator="kind")
]
