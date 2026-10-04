"""v13 orchestration: semantic routing before any resolver, source or vector access."""

import logging
from dataclasses import replace
from time import perf_counter

from fastapi import Request

from app.auth.credentials import extract_admin_credential
from app.auth.service import digest
from app.config import Settings
from app.errors import APIError
from app.research.answer_facts import project_answer_facts, render_conversation, render_facts
from app.research.context import ResearchExecutionContext
from app.research.conversation import summarize_plan
from app.research.conversation_state import ConversationState, ConversationStore
from app.research.geography import location_sensitive
from app.research.normalize_v12 import normalize_v12
from app.research.public_result import public_execution_result
from app.research.wire.research_v13_schema import (
    ConversationInteractionV13,
    ConversationV13,
    PlanResponseV13,
)
from app.schemas.research_conversation_v12 import ResearchPlanSummaryV12
from app.schemas.research_location import ResearchQueryRequest
from app.schemas.research_response import ConversationResponse, ResearchExecutionResponse
from app.services.research_plan_execution import ResearchPlanExecutor
from app.services.research_planner import ResearchPlannerClient, invalid_response


def conversation_response(
    token: str,
    state: ConversationState,
    interaction: ConversationInteractionV13,
) -> ConversationResponse:
    return ConversationResponse(
        conversation_id=token,
        language=state.language,
        interaction=interaction,
        answer_text=render_conversation(
            interaction.conversation, state.language, facts=state.facts, variant=state.turns
        ),
    )


async def execute_conversation(
    request: Request,
    settings: Settings,
    body: ResearchQueryRequest,
    planner: ResearchPlannerClient,
) -> ConversationResponse | ResearchExecutionResponse:
    if body.conversation_context is not None:
        raise APIError(422, "invalid_input", "v13 conversation context is owned by the backend.")
    credential = extract_admin_credential(request, settings)
    if credential is None:
        raise APIError(401, "authentication_required", "Authentication is required.")
    owner = digest(credential.source + ":" + credential.token)
    store: ConversationStore = request.app.state.research_conversations
    with store.turn(owner, body.conversation_id) as (token, state, expired):
        started = perf_counter()
        response = await planner.plan_natural(
            body.query,
            state.context(),
            language=state.language,
            pending=state.pending,
            previous_answer_available=state.facts is not None,
        )
        # Revalidate injected providers too. Invalid structure stays a 502; uncertainty
        # belongs in the valid clarification branch and is never repaired here.
        try:
            response = PlanResponseV13.model_validate_json(
                response.model_dump_json(), context={"original_query": body.query}
            )
            if response.timezone != settings.event_timezone:
                raise ValueError("planner_timezone_mismatch")
        except (ValueError, TypeError, AttributeError):
            raise invalid_response() from None
        planner_ms = (perf_counter() - started) * 1000
        interaction = response.plan.interaction
        state.language = response.plan.language
        state.turns += 1
        logging.getLogger("admin.research_planner").info(
            "research_conversation_route",
            extra={
                "interaction_kind": interaction.kind,
                "validation_stage": "validated",
            },
        )
        if expired:
            return conversation_response(
                token,
                state,
                ConversationInteractionV13(
                    kind="clarification",
                    conversation=ConversationV13(act="clarify", reason="needs_context"),
                ),
            )
        if isinstance(interaction, ConversationInteractionV13):
            # This branch cannot reach normalization, resolution, SQL, Qdrant or learning.
            if interaction.conversation.act not in {
                "acknowledge",
                "pleased",
                "repeat_previous",
                "simplify_previous",
                "explain_previous",
            }:
                state.facts = None
            if interaction.conversation.act == "unsupported":
                state.remember(None)
                state.pending = None
            return conversation_response(token, state, interaction)
        wire = interaction.research_plan
        if wire.unsupported_reason is not None:
            state.remember(None)
            state.pending = None
            state.facts = None
        if wire.unsupported_reason is not None or wire.clarification not in {
            "none",
            "needs_location",
        }:
            if wire.unsupported_reason is None and wire.clarification != "needs_context":
                try:
                    pending_plan = normalize_v12(wire)
                    pending = summarize_plan(
                        replace(pending_plan, clarification="none"), administrative=True
                    )
                    state.pending = pending if isinstance(pending, ResearchPlanSummaryV12) else None
                except APIError:
                    state.pending = None
            reason = wire.unsupported_reason or wire.clarification
            assert reason != "none"
            return conversation_response(
                token,
                state,
                ConversationInteractionV13(
                    kind="clarification",
                    conversation=ConversationV13(
                        act="unsupported" if wire.unsupported_reason else "clarify",
                        reason=reason,
                    ),
                ),
            )
        try:
            internal = normalize_v12(wire)
        except APIError as exc:
            if exc.code not in {"research_execution_unsupported", "research_plan_unsupported"}:
                raise
            state.remember(None)
            state.pending = None
            state.facts = None
            return conversation_response(
                token,
                state,
                ConversationInteractionV13(
                    kind="clarification",
                    conversation=ConversationV13(
                        act="unsupported", reason="unsupported_constraint"
                    ),
                ),
            )
        context = ResearchExecutionContext(
            reference_date=response.reference_date,
            timezone=response.timezone,
            original_query=body.query,
            location_context=body.location_context,
        )
        outcome = await ResearchPlanExecutor().execute(
            request, settings, internal, context, planner_ms=planner_ms
        )
        sensitive = body.location_context is not None or location_sensitive(
            internal.spatial_constraints
        )
        summary = summarize_plan(internal, administrative=True) if not sensitive else None
        assert summary is None or isinstance(summary, ResearchPlanSummaryV12)
        facts = project_answer_facts(internal, outcome.result, outcome.execution)
        if outcome.result.kind == "needs_clarification":
            state.pending = summary
        else:
            state.remember(summary)
            state.pending = None
        state.facts = facts if not sensitive else None
        # Never expose the semantic state; only a random opaque handle leaves Admin.
        # v13 conversation turns are excluded from suggestion learning entirely.
        return ResearchExecutionResponse(
            conversation_id=token,
            language=state.language,
            conversation_summary=None,
            answer_text=render_facts(facts, state.language, variant=state.turns),
            query=body.query,
            plan=response,
            resolution=outcome.resolution,
            result=public_execution_result(outcome.result),
            execution=outcome.execution,
            sql_provenance=outcome.sql_provenance,
            observed_at=outcome.observed_at,
            timezone=context.timezone,
            diagnostics=outcome.diagnostics,
        )
