"""Validated wire -> domain adapters. No lookup, inference or contract repair."""

from datetime import time
from typing import Literal

from app.errors import APIError
from app.research.geography import (
    AdministrativeAreaRef,
    NamedPlaceRef,
    SpatialConstraint,
    UserLocationRef,
)
from app.research.plan import (
    ComparisonTarget,
    InternalResearchPlan,
    NameFilters,
    SemanticSelection,
    TemporalSelection,
)
from app.schemas.research_analytics import (
    AnalyticalEnvelope,
    AnalyticalPlanResponse,
    AnalyticalQueryPlan,
)
from app.schemas.research_analytics_guard import analytical_mismatch
from app.schemas.research_geography import GeographicEnvelope, GeographicPlanResponse
from app.schemas.research_planner import PlanResponse, ResearchQueryPlan

PlannerResponse = PlanResponse | AnalyticalPlanResponse | GeographicPlanResponse


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
    query: str | None, relation: Literal["inside", "outside"]
) -> tuple[SpatialConstraint, ...]:
    return (SpatialConstraint(relation, AdministrativeAreaRef(query)),) if query else ()


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
    # Envelope consistency is validated by the transport. Retain the guard for
    # internal/injected callers without leaking disposition into the domain.
    if (response.kind == "plan") != (response.plan.clarification == "none"):
        raise APIError(502, "research_execution_invalid_plan", "The research plan is invalid.")
    if isinstance(response, GeographicEnvelope):
        return normalize_v6(response)
    if isinstance(response, AnalyticalEnvelope):
        return normalize_v5(response)
    return normalize_v3(response)


# v7 wire support lands here, executor unchanged. Add normalize_v7 with a closed,
# validated wire type when coordinated; do not accept arbitrary dictionaries or
# provisionally interpret unknown fields. There is no v7 transport/flag in this PR.
