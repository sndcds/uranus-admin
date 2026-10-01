"""Admin remains the only exact-data executor and public Research orchestrator."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Request

from app.admin_database import connect_admin
from app.config import Settings
from app.database import get_connection
from app.errors import APIError
from app.repositories.research_areas import resolve_area
from app.repositories.research_metrics import rank_metric
from app.repositories.research_resolution import candidates
from app.schemas.research_domain import PlanEnvelopeV4
from app.schemas.research_execution import ExecutionFilters
from app.schemas.research_unified import DataAnswer, UnifiedAnswer
from app.services.research_domain_client import ResearchDomainClient


async def execute(request: Request, settings: Settings, query: str) -> UnifiedAnswer:
    client: ResearchDomainClient | None = request.app.state.research_domain
    if client is None or not settings.research_domain_enabled:
        raise APIError(503, "research_domain_unavailable", "Research v4 is not enabled.")
    envelope = await client.plan(query)
    # Revalidate even injected providers; model_construct/copy are not trust boundaries.
    try:
        envelope = PlanEnvelopeV4.model_validate_json(envelope.model_dump_json())
        if envelope.original_query != query:
            raise ValueError
        if envelope.plan.domain == "project_knowledge" and envelope.plan.knowledge_query != query:
            raise ValueError
    except ValueError:
        raise APIError(502, "research_domain_invalid", "Invalid research plan.") from None
    plan = envelope.plan
    if plan.domain == "project_knowledge":
        return await client.answer(plan)
    async with asyncio.timeout(settings.db_timeout_seconds):
        area = None
        if plan.area_query:
            async with connect_admin(request) as admin, admin.begin():
                choices = await candidates(admin, "area", plan.area_query, settings)
                if len(choices) != 1:
                    raise APIError(
                        422, "research_area_ambiguous", "Select an unambiguous indexed area."
                    )
                area = await resolve_area(admin, UUID(choices[0].id))
        filters = ExecutionFilters(entity_type="event", area_id=area.area.id if area else None)
        async with asynccontextmanager(get_connection)(request) as connection:
            observed_at = datetime.now(UTC)
            records = await rank_metric(connection, settings, plan, filters, area)
        return DataAnswer(records=records, metric=plan, filters=filters, observed_at=observed_at)
