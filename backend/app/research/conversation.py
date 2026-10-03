"""Deliberate allowlist projection of executed intent, not response serialization."""

from dataclasses import asdict

from pydantic import ValidationError

from app.research.geography import UnresolvedAdministrativeAreaRef
from app.research.plan import InternalResearchPlan
from app.schemas.research_conversation import ResearchPlanSummary
from app.schemas.research_conversation_v12 import ResearchPlanSummaryV12


def summarize_plan(
    plan: InternalResearchPlan, *, administrative: bool = False
) -> ResearchPlanSummary | ResearchPlanSummaryV12 | None:
    # Do not partially remember a plan. Unrepresented/private semantics reset context.
    if (
        plan.intent == "compare"
        or plan.comparison_targets
        or plan.location_coverage
        or plan.zero_only
        or plan.clarification != "none"
        or plan.unsupported_reason
        or plan.temporal.time_from is not None
    ):
        return None
    areas = []
    for constraint in plan.spatial_constraints:
        ref = constraint.reference
        if (
            not isinstance(ref, UnresolvedAdministrativeAreaRef)
            or (not administrative and ref.expected_level is not None)
            or ref.country_code is not None
            or constraint.radius_m is not None
            or constraint.relation not in {"inside", "outside"}
        ):
            return None
        areas.append(
            {
                "name": ref.name,
                "relation": constraint.relation,
                **({"expected_level": ref.expected_level} if administrative else {}),
            }
        )
    temporal = asdict(plan.temporal)
    temporal.pop("time_from")
    temporal["weekdays"] = list(plan.temporal.weekdays)
    temporal["months"] = list(plan.temporal.months)
    try:
        return (ResearchPlanSummaryV12 if administrative else ResearchPlanSummary).model_validate(
            {
                "intent": plan.intent,
                "entity_type": plan.entity_type,
                "metric": plan.metric,
                "groupings": list(plan.groupings)
                if not administrative or plan.group_by == "none"
                else [plan.group_by],
                "ordering": plan.ordering,
                "limit": plan.limit,
                "temporal": temporal,
                "filters": {
                    "venue": plan.filters.venue_query,
                    "organization": plan.filters.organization_query,
                    "event_types": list(plan.filters.event_type_queries),
                    "categories": list(plan.filters.category_queries),
                    "genres": list(plan.filters.genre_queries),
                },
                "areas": areas,
                "semantic_query": plan.semantic.query if plan.semantic else None,
                "semantic_focus": plan.semantic.focus if plan.semantic else None,
                "taxonomy": plan.taxonomy,
                "spatial_metric": plan.spatial_metric,
            }
        )
    except ValidationError:
        return None
