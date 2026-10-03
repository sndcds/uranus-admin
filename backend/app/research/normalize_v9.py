"""Lossless v9 wire adapter to existing Admin capabilities; no lookup or execution."""

from dataclasses import replace
from typing import Literal, cast

from app.research.capabilities import require_supported
from app.research.geography import (
    NamedPlaceRef,
    SpatialConstraint,
    UnresolvedAdministrativeAreaRef,
    UserLocationRef,
)
from app.research.normalize import unsupported
from app.research.plan import (
    ComparisonTarget,
    InternalResearchPlan,
    NameFilters,
    SemanticSelection,
    TemporalSelection,
)
from app.research.wire.research_v9_constraints import SpatialV9, TemporalV9
from app.research.wire.research_v9_schema import ResearchQueryPlanV9
from app.research.wire.research_v9_types import NameFilterV9, TimeFilterV9
from app.schemas.research_execution import ExecutionGrouping, ExecutionMetric

COUNT_ENTITY = {
    "event_count": "event",
    "occurrence_count": "event",
    "venue_count": "venue",
    "organization_count": "organization",
}
SCALAR_GROUPS = {"event", "venue", "organization", "category", "genre", "event_type"}
CELL_GROUPS = SCALAR_GROUPS | {"month", "municipality"}


def normalize_v9_temporal(
    value: TemporalV9 | None, clocks: list[TimeFilterV9]
) -> TemporalSelection:
    if len(clocks) > 1 or any(clock.operator != "gte" for clock in clocks):
        raise unsupported()
    time_from = clocks[0].value if clocks else None
    if value is None:
        return TemporalSelection(time_from=time_from)
    if (
        value.field != "start_date"
        or value.calendar_relation != "none"
        or any(
            (
                value.before_time,
                value.after_time,
                value.weekday,
                value.overlap,
                value.multi_day,
                value.lookback,
                value.lookback_unit,
                value.calendar_area_query,
            )
        )
    ):
        # time_from is inclusive; v9 after_time cannot silently become >=.
        raise unsupported()
    return TemporalSelection(
        time_from=time_from,
        period=value.period,
        from_date=value.from_date,
        to_date=value.to_date,
        time_of_day=value.time_of_day,
    )


def normalize_v9_spatial(value: SpatialV9 | None) -> tuple[SpatialConstraint, ...]:
    if value is None:
        return ()
    if value.radius_m is not None:
        raise unsupported()
    if value.reference == "named":
        if value.relation in {"inside", "outside"} and value.area_query is not None:
            return (
                SpatialConstraint(
                    cast(Literal["inside", "outside"], value.relation),
                    UnresolvedAdministrativeAreaRef(value.area_query),
                ),
            )
        if value.relation == "at" and value.place_query is not None:
            # v6 named-place selection already owns address/bbox/bounded-radius semantics.
            return (SpatialConstraint("inside", NamedPlaceRef(value.place_query)),)
    if value.reference == "user_location" and value.relation == "nearby":
        return (SpatialConstraint("nearby", UserLocationRef()),)
    raise unsupported()


def normalize_v9_filters(wire: ResearchQueryPlanV9) -> NameFilters:
    names: dict[str, str] = {}
    for predicate in wire.filters:
        if isinstance(predicate, TimeFilterV9):
            continue  # Validated and retained in TemporalSelection, never discarded.
        if (
            not isinstance(predicate, NameFilterV9)
            or predicate.operator != "eq"
            or predicate.field not in {"venue", "organization", "category", "event_type", "genre"}
            or predicate.field in names
        ):
            # Multiple v9 equality predicates are not the legacy taxonomy OR-list.
            raise unsupported()
        names[predicate.field] = predicate.value
    return NameFilters(
        venue_query=names.get("venue"),
        organization_query=names.get("organization"),
        category_queries=(names["category"],) if "category" in names else (),
        event_type_queries=(names["event_type"],) if "event_type" in names else (),
        genre_queries=(names["genre"],) if "genre" in names else (),
    )


def normalize_v9_comparison(wire: ResearchQueryPlanV9) -> tuple[ComparisonTarget, ...]:
    targets = []
    for target in wire.comparison_targets:
        if target.kind not in {"venue", "organization", "region"}:
            # Level-specific targets cannot lose their level in ComparisonTarget.
            raise unsupported()
        kind = "area" if target.kind == "region" else target.kind
        targets.append(
            ComparisonTarget(cast(Literal["venue", "organization", "area"], kind), target.query)
        )
    return tuple(targets)


def normalize_v9(wire: ResearchQueryPlanV9) -> InternalResearchPlan:
    wire = ResearchQueryPlanV9.model_validate_json(wire.model_dump_json())
    if (
        wire.unsupported_reason is not None
        or wire.clarification not in {"none", "needs_criteria", "needs_location", "needs_date"}
        or wire.intent
        not in {"list", "search", "count", "aggregate", "rank", "compare", "taxonomy"}
        or any((wire.price, wire.relation, wire.trend, wire.anomaly, wire.explain, wire.knowledge))
    ):
        raise unsupported()
    # This base holds only constraints common to all existing executable families.
    # The family adapter below must validate entity, metric, grouping and all consumers.
    plan = InternalResearchPlan(
        intent=wire.intent,
        entity_type="event",
        filters=normalize_v9_filters(wire),
        temporal=normalize_v9_temporal(
            wire.temporal, [f for f in wire.filters if isinstance(f, TimeFilterV9)]
        ),
        spatial_constraints=normalize_v9_spatial(wire.spatial),
        ordering=wire.ordering,
        limit=wire.limit,
        clarification=cast(
            Literal["none", "needs_criteria", "needs_location", "needs_date"], wire.clarification
        ),
    )
    if wire.intent == "rank" and wire.metric is None and wire.clarification == "needs_criteria":
        if (
            wire.entity_type not in {"event", "venue", "organization"}
            or not set(wire.group_by) <= SCALAR_GROUPS
        ):
            raise unsupported()
        # No metric is invented. The shared executor returns clarification before
        # any capability dispatch/resolution; a later request is validated afresh.
        return replace(
            plan,
            entity_type=cast(Literal["event", "venue", "organization"], wire.entity_type),
            groupings=tuple(cast(ExecutionGrouping, d) for d in wire.group_by),
        )
    if wire.intent in {"list", "search", "taxonomy"}:
        if (
            wire.entity_type not in {"event", "venue", "organization"}
            or wire.metric_filter is not None
        ):
            raise unsupported()
        if wire.intent in {"search", "taxonomy"} and wire.entity_type != "event":
            raise unsupported()
        plan = replace(
            plan,
            entity_type=cast(Literal["event", "venue", "organization"], wire.entity_type),
            taxonomy=wire.taxonomy,
            semantic=SemanticSelection(wire.semantic.query, wire.semantic.focus)
            if wire.semantic
            else None,
        )
    elif wire.metric and wire.metric.operation == "value":
        # Ranking records by one authoritative field is the existing records primitive.
        if (
            wire.intent != "rank"
            or wire.metric_filter is not None
            or wire.group_by not in ([], [wire.entity_type])
        ):
            raise unsupported()
        if wire.metric.field == "start_date" and wire.entity_type == "event":
            plan = replace(plan, intent="list")
        elif wire.metric.field in {"longitude", "latitude"} and wire.entity_type in {
            "event",
            "venue",
        }:
            plan = replace(
                plan,
                intent="spatial_rank",
                entity_type=cast(Literal["event", "venue"], wire.entity_type),
                spatial_metric=cast(Literal["longitude", "latitude"], wire.metric.field),
            )
        else:
            raise unsupported()
    else:
        plan = normalize_v9_counts(wire, plan)
    require_supported(plan)
    return plan


def normalize_v9_counts(
    wire: ResearchQueryPlanV9, plan: InternalResearchPlan
) -> InternalResearchPlan:
    operation: str | None = wire.metric.operation if wire.metric else None
    if wire.metric and operation == "distinct_count":
        operation = {
            "event": "event_count",
            "occurrence": "occurrence_count",
            "venue": "venue_count",
            "organization": "organization_count",
        }.get(wire.metric.distinct_by or "")
        if operation is None or (
            wire.intent == "count" and wire.entity_type != wire.metric.distinct_by
        ):
            raise unsupported()
    if operation is None and wire.intent == "compare" and wire.clarification != "none":
        if (
            wire.entity_type not in {"event", "venue", "organization"}
            or wire.group_by
            or wire.metric_filter
        ):
            raise unsupported()
        return replace(
            plan,
            entity_type=cast(Literal["event", "venue", "organization"], wire.entity_type),
            comparison_targets=normalize_v9_comparison(wire),
        )
    if operation not in COUNT_ENTITY:
        raise unsupported()
    metric = cast(ExecutionMetric, operation)
    entity = cast(Literal["event", "venue", "organization"], COUNT_ENTITY[metric])
    plan = replace(plan, metric=metric, entity_type=entity)
    if wire.intent == "compare":
        if wire.group_by or wire.metric_filter or wire.limit is not None:
            raise unsupported()
        if wire.entity_type not in {
            entity,
            "occurrence" if metric == "occurrence_count" else entity,
            *(t.kind for t in wire.comparison_targets),
        }:
            raise unsupported()
        return replace(plan, comparison_targets=normalize_v9_comparison(wire))
    if wire.intent == "count":
        if wire.metric_filter is not None:
            raise unsupported()
        return plan  # Strict wire validation checked the counted entity.
    if wire.intent not in {"aggregate", "rank"} or not wire.group_by:
        raise unsupported()
    dimensions = tuple(wire.group_by)
    # Existing administrative catalog primitive, including its zero-event inventory.
    if (
        len(dimensions) == 1
        and dimensions[0] in {"region", "country", "municipality"}
        and (
            wire.entity_type in {"region", "municipality"} or dimensions[0] in {"region", "country"}
        )
    ):
        level = dimensions[0]
        if metric != "event_count" or wire.entity_type not in {
            "event",
            "region" if level == "country" else level,
        }:
            raise unsupported()
        if wire.metric_filter and (
            wire.metric_filter.operator != "eq" or wire.metric_filter.value != 0
        ):
            raise unsupported()
        return replace(
            plan,
            group_by=cast(Literal["region", "country", "municipality"], level),
            location_coverage=True,
            zero_only=wire.metric_filter is not None,
            ordering=wire.ordering or "desc",
            limit=wire.limit or 20,
        )
    if wire.metric_filter is not None:
        raise unsupported()
    measured_entities = {entity, "occurrence"} if entity == "event" else {entity}
    ranked_subject = (
        wire.intent == "rank" and len(dimensions) == 1 and wire.entity_type == dimensions[0]
    )
    if wire.entity_type not in measured_entities and not ranked_subject:
        raise unsupported()
    if len(dimensions) == 1 and dimensions[0] in SCALAR_GROUPS:
        if dimensions[0] == "event" and metric != "occurrence_count":
            raise unsupported()
        return replace(
            plan,
            intent="aggregate",
            group_by=cast(
                Literal["event", "venue", "organization", "category", "genre", "event_type"],
                dimensions[0],
            ),
        )
    if (
        entity != "event"
        or metric not in {"event_count", "occurrence_count"}
        or not set(dimensions) <= CELL_GROUPS
    ):
        raise unsupported()
    return replace(plan, groupings=tuple(cast(ExecutionGrouping, d) for d in dimensions))
