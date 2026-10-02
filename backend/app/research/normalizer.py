"""Interpret only validated wire fields; unsupported constraints fail as a whole."""

from typing import Literal, cast

from app.errors import APIError
from app.research.internal_plan import (
    LEVELS,
    AdministrativeLevel,
    AreaRequest,
    InternalResearchPlan,
    SpatialConstraint,
)
from app.research.wire.research_v8_schema import ResearchQueryPlanV8
from app.research.wire.research_v8_types import NameFilterV8


def unsupported() -> APIError:
    return APIError(422, "research_execution_unsupported", "This combination is not supported.")


def normalize_plan(wire: ResearchQueryPlanV8) -> InternalResearchPlan:
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
    grouping = cast(AdministrativeLevel, wire.group_by) if wire.group_by in LEVELS else None
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
                AreaRequest(geo.area_query, geo.area_level),
            )
        )
    return InternalResearchPlan(
        operation=cast(Literal["list", "count", "rank", "aggregate"], wire.intent),
        subject=wire.entity_type,
        grouping=grouping,
        spatial=tuple(spatial),
        category=category,
        zero_only=wire.metric_filter is not None,
        ordering=wire.ordering or "desc",
        limit=wire.limit or 20,
    )
