"""Versioned transport edge; execution belongs to the shared ResearchPlanExecutor."""

from time import perf_counter

from fastapi import Request

from app.config import Settings
from app.errors import APIError
from app.research.context import ResearchExecutionContext
from app.research.normalize import normalize_v8
from app.research.wire.research_v8_schema import PlanResponseV8
from app.schemas.research_administrative_result import AdministrativeResult
from app.services.research_plan_execution import ResearchPlanExecutor
from app.services.research_planner import invalid_response, unavailable


async def execute(request: Request, settings: Settings, query: str) -> AdministrativeResult:
    planner = request.app.state.research_planner
    if planner is None:
        raise unavailable()
    started = perf_counter()
    response = await planner.plan_administrative(query)
    try:
        response = PlanResponseV8.model_validate_json(response.model_dump_json())
        if response.plan.original_query != query or response.timezone != settings.event_timezone:
            raise ValueError("Planner identity mismatch")
    except ValueError:
        raise invalid_response() from None
    plan = normalize_v8(response.plan)
    context = ResearchExecutionContext(response.reference_date, response.timezone, query)
    outcome = await ResearchPlanExecutor().execute(
        request, settings, plan, context, planner_ms=(perf_counter() - started) * 1000
    )
    if outcome.administrative is None:
        raise APIError(
            422, "research_plan_clarification", "The research question needs clarification."
        )
    return outcome.administrative
