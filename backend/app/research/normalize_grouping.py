"""Wire adapters only; the shared executor owns all grouping capabilities."""

import json
from typing import Literal, cast

from app.research.geography import SpatialConstraint, UnresolvedAdministrativeAreaRef
from app.research.normalize import unsupported
from app.research.plan import InternalResearchPlan, NameFilters, TemporalSelection
from app.research.wire.research_v7_schema import ResearchQueryPlanV7
from app.research.wire.research_v9_schema import ResearchQueryPlanV9
from app.research.wire.research_v9_types import NameFilterV9
from app.schemas.research_execution import ExecutionGrouping


def normalize_v9(wire: ResearchQueryPlanV9) -> InternalResearchPlan:
    wire = ResearchQueryPlanV9.model_validate_json(wire.model_dump_json())
    if (
        wire.clarification != "none"
        or wire.unsupported_reason is not None
        or wire.intent not in {"aggregate", "rank"}
        or wire.entity_type not in {"event", "occurrence"}
        or not wire.group_by
        or wire.metric is None
        or wire.metric.operation not in {"event_count", "occurrence_count"}
        or any(
            (
                wire.price,
                wire.semantic,
                wire.relation,
                wire.trend,
                wire.anomaly,
                wire.explain,
                wire.knowledge,
                wire.comparison_targets,
                wire.taxonomy,
                wire.metric_filter,
            )
        )
    ):
        raise unsupported()
    if not set(wire.group_by) <= {
        "event",
        "venue",
        "organization",
        "category",
        "genre",
        "event_type",
        "month",
        "municipality",
    }:
        raise unsupported()
    names: dict[str, list[str]] = {}
    for predicate in wire.filters:
        if (
            not isinstance(predicate, NameFilterV9)
            or predicate.operator != "eq"
            or predicate.field not in {"venue", "organization", "category", "event_type", "genre"}
        ):
            raise unsupported()
        names.setdefault(predicate.field, []).append(predicate.value)
    if any(len(names.get(key, [])) > 1 for key in ("venue", "organization")):
        raise unsupported()
    temporal = TemporalSelection()
    if wire.temporal:
        t = wire.temporal
        if any((t.before_time, t.after_time, t.weekday, t.overlap, t.multi_day, t.lookback)) or (
            t.calendar_relation != "none" or t.field != "start_date"
        ):
            raise unsupported()
        temporal = TemporalSelection(
            period=t.period, from_date=t.from_date, to_date=t.to_date, time_of_day=t.time_of_day
        )
    spatial: tuple[SpatialConstraint, ...] = ()
    if wire.spatial:
        g = wire.spatial
        if g.relation not in {"inside", "outside"} or g.reference != "named" or not g.area_query:
            raise unsupported()
        spatial = (
            SpatialConstraint(
                cast(Literal["inside", "outside"], g.relation),
                UnresolvedAdministrativeAreaRef(g.area_query),
            ),
        )
    return InternalResearchPlan(
        intent=wire.intent,
        entity_type="event",
        metric=cast(Literal["event_count", "occurrence_count"], wire.metric.operation),
        groupings=tuple(cast(ExecutionGrouping, g) for g in wire.group_by),
        ordering=wire.ordering,
        limit=wire.limit,
        temporal=temporal,
        spatial_constraints=spatial,
        filters=NameFilters(
            venue_query=next(iter(names.get("venue", [])), None),
            organization_query=next(iter(names.get("organization", [])), None),
            category_queries=tuple(names.get("category", [])),
            event_type_queries=tuple(names.get("event_type", [])),
            genre_queries=tuple(names.get("genre", [])),
        ),
    )


def normalize_v7_grouping(wire: "ResearchQueryPlanV7") -> InternalResearchPlan:
    """Existing public scalar representation becomes one axis; no dimension inference."""

    validated = ResearchQueryPlanV7.model_validate_json(wire.model_dump_json())
    data = validated.model_dump(mode="json")
    data["group_by"] = [] if validated.group_by == "none" else [validated.group_by]
    return normalize_v9(ResearchQueryPlanV9.model_validate_json(json.dumps(data)))
