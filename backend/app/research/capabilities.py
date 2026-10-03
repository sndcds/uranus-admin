"""One version-independent capability gate. No natural-language interpretation."""

from app.errors import APIError
from app.research.geography import (
    ADMINISTRATIVE_LEVELS,
    NamedPlaceRef,
    UnresolvedAdministrativeAreaRef,
    UserLocationRef,
    administrative_constraints,
)
from app.research.plan import InternalResearchPlan

EXECUTABLE_INTENTS = frozenset(
    {
        "list",
        "search",
        "recommend",
        "count",
        "aggregate",
        "compare",
        "taxonomy",
        "spatial_rank",
    }
)


def unsupported(message: str) -> APIError:
    return APIError(422, "research_execution_unsupported", message)


def require_supported(plan: InternalResearchPlan) -> None:
    if plan.unsupported_reason is not None:
        raise APIError(422, "research_plan_unsupported", "This research plan is unsupported.")
    if grouped_execution(plan):
        require_supported_spatial(plan)
        return
    if (plan.intent not in EXECUTABLE_INTENTS and not boundary_execution(plan)) or any(
        value is not None
        for value in (
            plan.price,
            plan.relation,
            plan.trend,
            plan.anomaly,
            plan.explain,
            plan.knowledge,
        )
    ):
        raise unsupported("This research operation is not implemented.")
    if plan.semantic is not None and plan.entity_type != "event":
        raise unsupported("Semantic execution is supported only for events.")
    if plan.semantic is not None and plan.intent not in {"list", "search", "recommend"}:
        raise unsupported("Exact semantic counts, aggregates and comparisons are not supported.")
    require_supported_spatial(plan)
    if boundary_execution(plan):
        if (
            plan.entity_type != "event"
            or plan.semantic is not None
            or plan.comparison_targets
            or plan.taxonomy is not None
            or plan.spatial_metric is not None
            or plan.metric not in {"none", "event_count"}
            or (plan.intent == "list" and plan.group_by != "none")
            or (
                plan.intent == "count" and (plan.metric != "event_count" or plan.group_by != "none")
            )
            or (
                plan.intent in {"rank", "aggregate"}
                and (plan.group_by not in ADMINISTRATIVE_LEVELS or plan.metric != "event_count")
            )
            or plan.intent not in {"list", "count", "rank", "aggregate"}
            or (plan.zero_only and plan.group_by not in ADMINISTRATIVE_LEVELS)
        ):
            raise unsupported("This administrative selection is not implemented.")
        return
    areas = administrative_constraints(plan.spatial_constraints)
    if plan.group_by in {"area", "region", "municipality", "district", "state", "country"}:
        raise unsupported("Area grouping requires an explicit non-overlapping area level.")
    # Common filters intersect each target; a target must never overwrite one.
    if any(
        (t.kind == "area" and areas)
        or (t.kind == "venue" and plan.filters.venue_query)
        or (t.kind == "organization" and plan.filters.organization_query)
        for t in plan.comparison_targets
    ):
        raise unsupported("Comparison targets cannot replace a common filter of the same type.")


def require_supported_spatial(plan: InternalResearchPlan) -> None:
    areas = administrative_constraints(plan.spatial_constraints)
    # Polygon membership accepts bounded AND predicates, never the OR union
    # produced by resolve_areas(). Point/place mixing remains unsupported.
    if (
        (len(areas) > 4 or len(plan.spatial_constraints) != len(areas))
        if boundary_execution(plan)
        else (len(plan.spatial_constraints) - len(areas) > 1)
    ):
        raise unsupported("This combination of spatial references is not executable.")
    for constraint in plan.spatial_constraints:
        reference = constraint.reference
        if constraint.radius_m is not None or not (
            (
                isinstance(reference, UnresolvedAdministrativeAreaRef)
                and constraint.relation in {"inside", "outside"}
            )
            or (isinstance(reference, NamedPlaceRef) and constraint.relation == "inside")
            or (isinstance(reference, UserLocationRef) and constraint.relation == "nearby")
        ):
            raise unsupported("This spatial predicate is not implemented.")


def boundary_execution(plan: InternalResearchPlan) -> bool:
    """Choose a generic polygon/inventory primitive, never a Planner version."""
    return (
        plan.location_coverage
        or "municipality" in plan.groupings
        or any(
            isinstance(c.reference, UnresolvedAdministrativeAreaRef)
            and c.reference.country_code is not None
            for c in plan.spatial_constraints
        )
        or plan.group_by in ADMINISTRATIVE_LEVELS
        or len(administrative_constraints(plan.spatial_constraints)) > 1
    )


def grouped_execution(plan: InternalResearchPlan) -> bool:
    """Cell aggregation primitive, selected by capabilities, never wire version."""
    return (
        bool(plan.groupings)
        and plan.group_by == "none"
        and plan.intent in {"aggregate", "rank"}
        and plan.entity_type == "event"
        and plan.metric in {"event_count", "occurrence_count"}
        and set(plan.groupings)
        <= {
            "event",
            "venue",
            "organization",
            "category",
            "event_type",
            "genre",
            "month",
            "weekday",
            "municipality",
        }
        and not ("event" in plan.groupings and plan.metric != "occurrence_count")
        and not any(
            (
                plan.semantic,
                plan.relation,
                plan.trend,
                plan.anomaly,
                plan.explain,
                plan.knowledge,
                plan.price,
                plan.comparison_targets,
                plan.taxonomy,
                plan.spatial_metric,
                plan.zero_only,
            )
        )
    )
