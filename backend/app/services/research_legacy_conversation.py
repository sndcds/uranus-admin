"""Server-owned context for v11/v12 rollback; older browser contracts remain accepted."""

import json
from collections.abc import Awaitable, Callable

from fastapi import Request

from app.auth.credentials import extract_admin_credential
from app.auth.service import digest
from app.config import Settings
from app.errors import APIError
from app.research.conversation_state import ConversationStore
from app.schemas.research_conversation import ResearchConversationContext
from app.schemas.research_conversation_v12 import ResearchPlanSummaryV12
from app.schemas.research_location import ResearchQueryRequest
from app.schemas.research_response import ResearchExecutionResponse


async def legacy_turn(
    request: Request,
    settings: Settings,
    body: ResearchQueryRequest,
    execute: Callable[[ResearchQueryRequest], Awaitable[ResearchExecutionResponse]],
) -> ResearchExecutionResponse:
    credential = extract_admin_credential(request, settings)
    if credential is None:
        raise APIError(401, "authentication_required", "Authentication is required.")
    store: ConversationStore = request.app.state.research_conversations
    with store.turn(digest(credential.source + ":" + credential.token), body.conversation_id) as (
        token,
        state,
        expired,
    ):
        if expired:
            raise APIError(
                422, "research_execution_unsupported", "Please start a new conversation."
            )
        context = state.context()
        if context is not None and settings.research_planner_contract == "v11":
            data = context.model_dump(mode="json")
            for summary in data["previous_turns"]:
                for area in summary["areas"]:
                    if area.pop("expected_level") is not None:
                        raise APIError(
                            422, "research_execution_unsupported", "Context requires v12."
                        )
            legacy_context = ResearchConversationContext.model_validate_json(json.dumps(data))
        else:
            legacy_context = None
        response = await execute(
            body.model_copy(
                update={
                    "conversation_id": None,
                    "conversation_context": legacy_context
                    if legacy_context is not None
                    else context,
                }
            )
        )
        summary = response.conversation_summary
        if summary is not None:
            data = summary.model_dump(mode="json")
            for area in data["areas"]:
                area.setdefault("expected_level", None)
            state.remember(ResearchPlanSummaryV12.model_validate_json(json.dumps(data)))
        else:
            state.remember(None)
        return response.model_copy(update={"conversation_id": token})
