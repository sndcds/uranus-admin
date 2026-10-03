"""Validated wire -> domain adapters. No lookup, inference or contract repair."""

from datetime import time
from typing import Literal, cast

from app.errors import APIError
from app.research.geography import (
    ADMINISTRATIVE_LEVELS,
    AdministrativeLevel,
    NamedPlaceRef,
    SpatialConstraint,
    UnresolvedAdministrativeAreaRef,
    UserLocationRef,
)
from app.research.plan import (
    ComparisonTarget,
    InternalResearchPlan,
    NameFilters,
    SemanticSelection,
    TemporalSelection,
)
from app.research.wire.research_v8_schema import ResearchQueryPlanV8
from app.research.wire.research_v8_types import NameFilterV8
from app.research.wire.research_v9_schema import PlanResponseV9
from app.research.wire.research_v10_schema import PlanResponseV10
from app.schemas.research_analytics import (
    AnalyticalEnvelope,
    AnalyticalPlanResponse,
    AnalyticalQueryPlan,
)
from app.schemas.research_analytics_guard import analytical_mismatch
from app.schemas.research_geography import GeographicEnvelope, GeographicPlanResponse
from app.schemas.research_planner import PlanResponse, ResearchQueryPlan

PlannerResponse = (
    PlanResponse
    | AnalyticalPlanResponse
    | GeographicPlanResponse
    | PlanResponseV9
    | PlanResponseV10
)


def _common(
    plan: ResearchQueryPlan | AnalyticalQueryPlan,
    *,
    temporal: TemporalSelection,
    constraints: tuple[SpatialConstraint, ...],
    area_relation: Literal["inside", "outside"] = "inside",
    spatial_metric: Literal["longitude", "latitude"] | None = None,
    taxonomy: Literal["genre", "event_type", "category"] | None = None,
) -> InternalResearchPlan:
    if (
        plan.unsupported_reason is None
        and plan.clarification == "none"
        and analytical_mismatch(
            plan.original_query,
            plan.intent,
            plan.group_by,
            taxonomy,
            area_relation,
            plan.time_of_day,
        )
    ):
        # Preserve the existing rejection contract. Never change intent, fill a
        # missing metric or drop a constraint to make a plan executable.
        raise APIError(422, "research_plan_unsupported", "This research plan is unsupported.")
    return InternalResearchPlan(
        intent=plan.intent,
        entity_type=plan.entity_type,
        metric=plan.metric,
        group_by=plan.group_by,
        ordering=plan.ordering,
        limit=plan.limit,
        filters=NameFilters(
            venue_query=plan.venue_query,
            organization_query=plan.organization_query,
            event_type_queries=tuple(plan.event_type_queries),
            category_queries=tuple(plan.category_queries),
            genre_queries=tuple(plan.genre_queries),
        ),
        temporal=temporal,
        spatial_constraints=constraints,
        spatial_metric=spatial_metric,
        taxonomy=taxonomy,
        semantic=SemanticSelection(plan.semantic_query, plan.semantic_focus)
        if plan.semantic_query is not None
        else None,
        comparison_targets=tuple(
            ComparisonTarget(t.kind, t.query) for t in plan.comparison_targets
        ),
        clarification=plan.clarification,
        unsupported_reason=plan.unsupported_reason,
    )


def normalize_v3(response: PlanResponse) -> InternalResearchPlan:
    plan = response.plan
    return _common(
        plan,
        temporal=TemporalSelection(
            period=plan.temporal,
            from_date=plan.explicit_from_date,
            to_date=plan.explicit_to_date,
            time_from=time(18) if plan.time_of_day == "evening" else None,
        ),
        constraints=_area_constraints(plan.area_query, "inside"),
    )


def _area_constraints(
    query: str | None,
    relation: Literal["inside", "outside"],
    expected_level: AdministrativeLevel | None = None,
) -> tuple[SpatialConstraint, ...]:
    return (
        (SpatialConstraint(relation, UnresolvedAdministrativeAreaRef(query, expected_level)),)
        if query
        else ()
    )


def _analytical(
    plan: AnalyticalQueryPlan, constraints: tuple[SpatialConstraint, ...]
) -> InternalResearchPlan:
    return _common(
        plan,
        temporal=TemporalSelection(
            period=plan.temporal,
            from_date=plan.explicit_from_date,
            to_date=plan.explicit_to_date,
            time_of_day=plan.time_of_day,
        ),
        constraints=constraints,
        area_relation=plan.area_relation,
        spatial_metric=plan.spatial_metric,
        taxonomy=plan.taxonomy,
    )


def normalize_v5(response: AnalyticalPlanResponse) -> InternalResearchPlan:
    plan = response.plan
    return _analytical(plan, _area_constraints(plan.area_query, plan.area_relation))


def normalize_v6(response: GeographicPlanResponse) -> InternalResearchPlan:
    plan = response.plan
    constraints = _area_constraints(plan.area_query, plan.area_relation)
    if plan.place_query is not None:
        constraints += (SpatialConstraint("inside", NamedPlaceRef(plan.place_query)),)
    if plan.location_relation == "nearby":
        constraints += (SpatialConstraint("nearby", UserLocationRef()),)
    return _analytical(plan, constraints)


def normalize(response: PlannerResponse) -> InternalResearchPlan:
    if isinstance(response, PlanResponseV10):
        from app.research.normalize_v10 import normalize_v10

        return normalize_v10(response.plan)
    if isinstance(response, PlanResponseV9):
        from app.research.normalize_v9 import normalize_v9

        return normalize_v9(response.plan)
    # Envelope consistency is validated by the transport. Retain the guard for
    # internal/injected callers without leaking disposition into the domain.
    if (response.kind == "plan") != (response.plan.clarification == "none"):
        raise APIError(502, "research_execution_invalid_plan", "The research plan is invalid.")
    if isinstance(response, GeographicEnvelope):
        return normalize_v6(response)
    if isinstance(response, AnalyticalEnvelope):
        return normalize_v5(response)
    return normalize_v3(response)


# v7 wire normalization lands here with a closed, validated contract. Existing
# executable capabilities need no version-specific executor. New capabilities
# beyond the implemented families still require generic executor/repository work.
# Do not interpret unknown fields. There is no v7 transport/flag in this PR.


def unsupported() -> APIError:
    return APIError(422, "research_execution_unsupported", "This combination is not supported.")


def normalize_v8(wire: ResearchQueryPlanV8) -> InternalResearchPlan:
    wire = ResearchQueryPlanV8.model_validate_json(wire.model_dump_json())
    if wire.clarification != "none":
        raise APIError(
            422, "research_plan_clarification", "The research question needs clarification."
        )
    if wire.unsupported_reason is not None or any(
        (
            wire.temporal,
            wire.price,
            wire.semantic,
            wire.relation,
            wire.trend,
            wire.anomaly,
            wire.explain,
            wire.knowledge,
            wire.comparison_targets,
            wire.taxonomy,
        )
    ):
        raise unsupported()
    if wire.intent not in {"list", "count", "rank", "aggregate"}:
        raise unsupported()
    grouping = (
        cast(AdministrativeLevel, wire.group_by) if wire.group_by in ADMINISTRATIVE_LEVELS else None
    )
    if grouping is None:
        if (
            wire.entity_type != "event"
            or wire.group_by != "none"
            or wire.intent not in {"list", "count"}
        ):
            raise unsupported()
    elif wire.entity_type != grouping or wire.intent not in {"rank", "aggregate"}:
        raise unsupported()
    if wire.intent != "list" and (wire.metric is None or wire.metric.operation != "event_count"):
        raise unsupported()
    if wire.metric_filter is not None and (
        grouping is None or wire.metric_filter.operator != "eq" or wire.metric_filter.value != 0
    ):
        raise unsupported()
    category = None
    for predicate in wire.filters:
        if (
            not isinstance(predicate, NameFilterV8)
            or predicate.field != "category"
            or predicate.operator != "eq"
            or category is not None
        ):
            raise unsupported()
        category = predicate.value
    spatial = []
    for geo in wire.spatial:
        if (
            geo.relation not in {"inside", "outside"}
            or geo.reference != "named"
            or geo.area_query is None
        ):
            raise unsupported()
        spatial.append(
            SpatialConstraint(
                cast(Literal["inside", "outside"], geo.relation),
                UnresolvedAdministrativeAreaRef(geo.area_query, geo.area_level),
            )
        )
    return InternalResearchPlan(
        intent=cast(Literal["list", "count", "rank", "aggregate"], wire.intent),
        metric="event_count" if wire.metric is not None else "none",
        entity_type="event",
        group_by=grouping or "none",
        spatial_constraints=tuple(spatial),
        location_coverage=True,
        filters=NameFilters(category_queries=(category,) if category else ()),
        zero_only=wire.metric_filter is not None,
        ordering=wire.ordering or "desc",
        limit=wire.limit or 20,
    )
