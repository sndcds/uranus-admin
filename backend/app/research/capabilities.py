"""One version-independent capability gate. No natural-language interpretation."""

from app.errors import APIError
from app.research.geography import (
    AdministrativeAreaRef,
    NamedPlaceRef,
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
    if plan.intent not in EXECUTABLE_INTENTS or any(
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
    # Preserve every AND predicate. The current SQL primitive accepts one boundary;
    # do not accidentally substitute resolve_areas(), whose union means OR.
    if len(areas) > 1 or len(plan.spatial_constraints) - len(areas) > 1:
        raise unsupported("Multiple spatial references are not yet executable.")
    for constraint in plan.spatial_constraints:
        reference = constraint.reference
        if constraint.radius_m is not None or not (
            (
                isinstance(reference, AdministrativeAreaRef)
                and constraint.relation in {"inside", "outside"}
            )
            or (isinstance(reference, NamedPlaceRef) and constraint.relation == "inside")
            or (isinstance(reference, UserLocationRef) and constraint.relation == "nearby")
        ):
            raise unsupported("This spatial predicate is not implemented.")
