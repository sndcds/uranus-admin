"""Wire -> Normalizer -> InternalResearchPlan -> Resolver -> resolved-only Executor."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError

from app.clients.research_geocoder import ResearchGeocoderClient
from app.config import Settings
from app.database import get_connection
from app.errors import APIError
from app.repositories.administrative_execution import AdministrativeResult, execute_resolved
from app.repositories.research_resolution import candidates
from app.research.administrative_catalog import load_inventory
from app.research.administrative_resolver import resolve_administrative_area
from app.research.internal_plan import ResolvedResearchPlan, ResolvedSpatialConstraint
from app.research.normalizer import normalize_plan
from app.research.wire.research_v8_schema import PlanResponseV8
from app.services.research_planner import ResearchPlannerClient, invalid_response, unavailable


async def execute(request: Request, settings: Settings, query: str) -> AdministrativeResult:
    planner: ResearchPlannerClient | None = request.app.state.research_planner
    geocoder: ResearchGeocoderClient | None = request.app.state.research_geocoder
    if planner is None:
        raise unavailable()
    envelope = await planner.plan_administrative(query)
    try:
        envelope = PlanResponseV8.model_validate_json(envelope.model_dump_json())
        if envelope.plan.original_query != query or envelope.timezone != settings.event_timezone:
            raise ValueError
    except ValueError:
        raise invalid_response() from None
    plan = normalize_plan(envelope.plan)
    if plan.spatial and geocoder is None:
        raise APIError(503, "geocoder_unavailable", "Geographic resolution is unavailable.")
    try:
        spatial = []
        # Network resolution happens before opening any source transaction.
        async with asyncio.timeout(45):
            for constraint in plan.spatial:
                assert geocoder is not None
                area = await resolve_administrative_area(geocoder, constraint.area)
                spatial.append(ResolvedSpatialConstraint(constraint.relation, area))
            inventory, countries = (
                await load_inventory(
                    settings.research_administrative_catalog_path, plan.grouping, tuple(spatial)
                )
                if plan.grouping
                else ((), ())
            )
        category_id = None
        if plan.category is not None:
            async with asyncio.timeout(settings.db_timeout_seconds):
                async with asynccontextmanager(get_connection)(request) as source:
                    options = await candidates(source, "category", plan.category, settings)
                    if len(options) != 1:
                        raise APIError(
                            422, "research_category_ambiguous", "Select an unambiguous category."
                        )
                    category_id = int(options[0].id)
        resolved = ResolvedResearchPlan(
            operation=plan.operation,
            grouping=plan.grouping,
            spatial=tuple(spatial),
            category_id=category_id,
            zero_only=plan.zero_only,
            ordering=plan.ordering,
            limit=plan.limit,
            inventory=inventory,
            inventory_countries=countries,
        )
        async with asyncio.timeout(settings.db_timeout_seconds):
            async with asynccontextmanager(get_connection)(request) as source:
                return await execute_resolved(source, settings, resolved)
    except (SQLAlchemyError, TimeoutError):
        raise APIError(
            503, "research_execution_unavailable", "Research execution is unavailable."
        ) from None
