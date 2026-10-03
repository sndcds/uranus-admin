"""Research Query Language v7. Declarative interpretation, never an execution plan."""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationInfo, model_validator

from app.research.wire.research_v7_constraints import (
    AnomalyV7,
    ComparisonTargetV7,
    ExplainV7,
    KnowledgeV7,
    PriceV7,
    RelationV7,
    SemanticV7,
    SpatialV7,
    TemporalV7,
    TrendV7,
)
from app.research.wire.research_v7_types import (
    COUNT_OPERATIONS,
    ClosedV7,
    EntityV7,
    FilterV7,
    GroupingV7,
    IntentV7,
    MetricV7,
    NameFilterV7,
    NameV7,
    NumericPredicateV7,
    QueryV7,
    TaxonomyV7,
)


class ResearchQueryPlanV7(ClosedV7):
    original_query: QueryV7
    intent: IntentV7
    entity_type: EntityV7 | None
    metric: MetricV7 | None
    group_by: GroupingV7
    ordering: Literal["asc", "desc"] | None
    limit: Annotated[int, Field(ge=1, le=20)] | None
    filters: list[FilterV7] = Field(max_length=16)
    metric_filter: NumericPredicateV7 | None
    taxonomy: TaxonomyV7 | None
    temporal: TemporalV7 | None
    spatial: SpatialV7 | None
    price: PriceV7 | None
    semantic: SemanticV7 | None
    relation: RelationV7 | None
    trend: TrendV7 | None
    anomaly: AnomalyV7 | None
    explain: ExplainV7 | None
    knowledge: KnowledgeV7 | None
    comparison_targets: list[ComparisonTargetV7] = Field(max_length=4)
    clarification: Literal[
        "none",
        "needs_criteria",
        "needs_location",
        "needs_date",
        "needs_definition",
        "needs_context",
    ]
    unsupported_reason: (
        Literal[
            "outside_research",
            "unsupported_constraint",
            "insufficient_structured_data",
        ]
        | None
    )

    @model_validator(mode="after")
    def consistent_language(self, info: ValidationInfo) -> Self:
        # Context supplied by both trust boundaries, never by model JSON.
        if info.context is not None and self.original_query != info.context["original_query"]:
            raise ValueError("original_query_changed")
        operation = self.metric.operation if self.metric is not None else None
        blocked = self.clarification != "none" or self.unsupported_reason is not None
        if self.intent == "rank":
            unresolved_metric = self.unsupported_reason is not None or self.clarification in {
                "needs_definition",
                "needs_criteria",
            }
            if (
                self.ordering is None
                or self.limit is None
                or (self.metric is None and not unresolved_metric)
            ):
                raise ValueError("rank_requires_metric_order_and_limit")
        if (
            self.intent == "rank"
            and self.group_by
            in {"event", "occurrence", "venue", "space", "organization", "municipality", "region"}
            and self.entity_type != self.group_by
        ):
            raise ValueError("rank_entity_group_mismatch")
        if self.intent == "count":
            if operation not in COUNT_OPERATIONS | {"distinct_count"}:
                raise ValueError("count_requires_countable_metric")
            expected = {
                "event_count": "event",
                "occurrence_count": "occurrence",
                "venue_count": "venue",
                "space_count": "space",
                "organization_count": "organization",
            }.get(operation or "")
            if expected is not None and self.entity_type != expected:
                raise ValueError("count_entity_mismatch")
        if self.intent == "aggregate" and not blocked:
            if self.metric is None or (operation in COUNT_OPERATIONS and self.group_by == "none"):
                raise ValueError("aggregate_requires_metric_and_group")
        if (
            self.intent in {"list", "search", "taxonomy", "knowledge", "explain"}
            and self.metric is not None
        ):
            raise ValueError("unexpected_metric")
        if self.intent == "taxonomy" and self.taxonomy is None:
            raise ValueError("taxonomy_required")
        if self.taxonomy is not None and self.intent != "taxonomy":
            raise ValueError("unexpected_taxonomy")
        if self.intent == "relation" and self.relation is None and self.unsupported_reason is None:
            raise ValueError("relation_required")
        if self.relation is not None and self.intent not in {
            "relation",
            "rank",
            "count",
            "aggregate",
            "compare",
        }:
            raise ValueError("unexpected_relation")
        if (self.intent == "trend") != (self.trend is not None):
            raise ValueError("trend_required_or_unexpected")
        if self.trend is not None:
            if self.metric is not None and (
                operation != self.trend.change
                or self.metric.measure != self.trend.measure
                or self.metric.window != self.trend.window
            ):
                raise ValueError("trend_metric_mismatch")
        elif operation in {"absolute_change", "percentage_change"}:
            raise ValueError("change_requires_trend")
        if (
            self.intent == "anomaly"
            and self.anomaly is None
            and self.clarification != "needs_criteria"
        ):
            raise ValueError("anomaly_requires_constraint_or_criteria")
        if self.anomaly is not None:
            if self.intent != "anomaly":
                raise ValueError("unexpected_anomaly")
            if self.anomaly.kind == "outlier" and not blocked:
                raise ValueError("outlier_method_undefined")
            if (
                self.anomaly.kind in {"rare", "inactive"}
                and self.metric_filter is None
                and not blocked
            ):
                raise ValueError("anomaly_threshold_undefined")
            if not blocked:
                if self.anomaly.measure is None or operation != self.anomaly.measure:
                    raise ValueError("anomaly_requires_matching_count_measure")
                if self.anomaly.kind == "inactive" and (
                    self.temporal is None or self.temporal.period != "past"
                ):
                    raise ValueError("inactivity_requires_past_time_basis")
        if operation == "regularity" and not blocked:
            raise ValueError("regularity_method_undefined")
        if self.group_by != "none" and self.intent not in {
            "aggregate",
            "rank",
            "compare",
            "trend",
            "anomaly",
        }:
            raise ValueError("unexpected_grouping")
        if self.group_by == "event" and operation == "event_count":
            raise ValueError("event_count_per_event_is_meaningless")
        if self.metric_filter is not None and self.metric is None:
            raise ValueError("metric_filter_requires_metric")
        if self.ordering is not None and self.intent not in {
            "rank",
            "aggregate",
            "trend",
            "taxonomy",
            "anomaly",
        }:
            raise ValueError("unexpected_ordering")
        if self.limit is not None and self.intent in {"count", "explain", "knowledge"}:
            raise ValueError("unexpected_limit")
        if self.intent == "search" and self.semantic is None:
            raise ValueError("search_requires_semantic_constraint")
        if self.semantic is not None:
            if (
                self.intent != "search"
                and self.unsupported_reason != "insufficient_structured_data"
            ):
                raise ValueError("semantic_exact_population_forbidden")
        if self.spatial is not None:
            geo = self.spatial
            if geo.reference == "user_location" and self.clarification != "needs_location":
                raise ValueError("deictic_geography_requires_location")
            named = geo.place_query is not None or geo.area_query is not None
            if geo.reference in {"named", "border"} and not named and not blocked:
                raise ValueError("spatial_reference_requires_clarification")
            if geo.relation == "near_border" and geo.radius_m is None and not blocked:
                raise ValueError("border_distance_requires_definition")
        if operation == "distance" and self.spatial is None:
            raise ValueError("distance_requires_spatial_reference")
        if self.temporal is not None and self.temporal.calendar_relation != "none":
            if self.temporal.calendar_area_query is None and self.clarification != "needs_location":
                raise ValueError("calendar_requires_jurisdiction")
        if self.intent == "compare":
            if len(self.comparison_targets) == 1 or (
                not blocked and len(self.comparison_targets) < 2
            ):
                raise ValueError("comparison_requires_two_to_four_targets")
            if not blocked and self.metric is None:
                raise ValueError("comparison_requires_metric")
        elif self.comparison_targets:
            raise ValueError("unexpected_comparison_targets")
        targets = [(t.kind, t.query.strip().casefold()) for t in self.comparison_targets]
        if len(set(targets)) != len(targets):
            raise ValueError("duplicate_comparison_targets")
        filter_keys = [f.model_dump_json() for f in self.filters]
        if len(set(filter_keys)) != len(filter_keys):
            raise ValueError("duplicate_filters")
        names = [
            (f.field, f.value.strip().casefold())
            for f in self.filters
            if isinstance(f, NameFilterV7)
        ]
        if len(set(names)) != len(names):
            raise ValueError("duplicate_or_conflicting_name_filters")
        presence = [(f.field, getattr(f, "operator", None)) for f in self.filters]
        for field, op in presence:
            if op == "missing" and (field, "present") in presence:
                raise ValueError("conflicting_presence_filters")
        if self.intent in {"knowledge", "explain"}:
            if self.entity_type is not None or any(
                (
                    self.filters,
                    self.metric,
                    self.metric_filter,
                    self.taxonomy,
                    self.temporal,
                    self.spatial,
                    self.price,
                    self.semantic,
                    self.relation,
                    self.trend,
                    self.anomaly,
                )
            ):
                raise ValueError("non_data_intent_has_data_constraints")
        elif self.entity_type is None and self.unsupported_reason is None:
            raise ValueError("data_intent_requires_entity")
        if (self.intent == "knowledge") != (self.knowledge is not None):
            raise ValueError("knowledge_required_or_unexpected")
        if (self.intent == "explain") != (self.explain is not None):
            raise ValueError("explain_required_or_unexpected")
        if (
            self.explain is not None
            and self.explain.context == "previous_result"
            and self.clarification != "needs_context"
        ):
            raise ValueError("explanation_requires_result_context")
        if self.unsupported_reason == "outside_research":
            if (
                self.intent != "list"
                or self.entity_type is not None
                or self.clarification != "none"
                or any(
                    (
                        self.metric,
                        self.filters,
                        self.metric_filter,
                        self.taxonomy,
                        self.temporal,
                        self.spatial,
                        self.price,
                        self.semantic,
                        self.relation,
                        self.trend,
                        self.anomaly,
                        self.explain,
                        self.knowledge,
                        self.comparison_targets,
                        self.ordering,
                        self.limit,
                    )
                )
                or self.group_by != "none"
            ):
                raise ValueError("outside_research_requires_neutral_plan")
        return self


class DiagnosticsV7(ClosedV7):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    planner_intent: IntentV7
    planner_model: NameV7
    planner_prompt_version: Literal["research-planner-v13"]
    planner_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)


class PlanResponseV7(ClosedV7):
    kind: Literal["plan", "needs_clarification", "unsupported"]
    schema_version: Literal["research-query-plan-v7"]
    prompt_version: Literal["research-planner-v13"]
    model: NameV7
    plan: ResearchQueryPlanV7
    reference_date: date
    timezone: str = Field(max_length=64)
    diagnostics: DiagnosticsV7

    @model_validator(mode="after")
    def disposition(self) -> Self:
        expected = (
            "unsupported"
            if self.plan.unsupported_reason is not None
            else "needs_clarification"
            if self.plan.clarification != "none"
            else "plan"
        )
        if self.kind != expected or self.diagnostics.planner_intent != self.plan.intent:
            raise ValueError("envelope_disposition_mismatch")
        return self
