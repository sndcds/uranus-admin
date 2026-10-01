"""Best-effort learning after successful execution, isolated from source reads."""

import asyncio
import logging
from uuid import UUID

from fastapi import Request

from app.admin_database import connect_admin
from app.repositories.research_suggestions import learn
from app.schemas.research_execution import ResearchExecutionResponse


async def record_success(
    request: Request, response: ResearchExecutionResponse, receipt: UUID | None
) -> None:
    if response.result.kind == "needs_clarification" or response.plan.plan.unsupported_reason:
        return
    try:
        async with (
            asyncio.timeout(1.0),
            connect_admin(request) as connection,
            connection.begin(),
        ):
            await learn(connection, response.query, response.plan.plan, receipt)
    except Exception:
        # No exception text, query, planner slots, identity or correlation values in logs.
        logging.getLogger("admin").warning("research_learning_unavailable")
