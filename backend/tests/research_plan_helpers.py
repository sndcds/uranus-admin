"""Existing execution regressions cross the same boundary as the HTTP route."""

from app.research.context import ResearchExecutionContext
from app.research.normalize import PlannerResponse, normalize
from app.research.plan import InternalResearchPlan
from app.schemas.research_location import LocationContext


def plan_context(
    response: PlannerResponse, location_context: LocationContext | None = None
) -> tuple[InternalResearchPlan, ResearchExecutionContext]:
    return normalize(response), ResearchExecutionContext(
        reference_date=response.reference_date,
        timezone=response.timezone,
        original_query=response.plan.original_query,
        location_context=location_context,
    )
