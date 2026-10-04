"""Closed conversational envelope around the unchanged v12 research algebra."""

from datetime import date
from typing import Literal, Self

from pydantic import Field, ValidationInfo, model_validator

from app.research.wire.research_v9_types import ClosedV9, NameV9, QueryV9
from app.research.wire.research_v12_schema import ResearchQueryPlanV12

AnswerLanguage = Literal["de", "da", "en"]
InteractionKind = Literal[
    "research",
    "acknowledgement",
    "greeting",
    "social",
    "help",
    "correction",
    "clarification_response",
    "clarification",
]


class ResearchInteractionV13(ClosedV9):
    kind: Literal["research", "correction", "clarification_response"]
    research_mode: Literal["new", "follow_up", "correction", "clarification_response"]
    research_plan: ResearchQueryPlanV12

    @model_validator(mode="after")
    def mode_matches_kind(self) -> Self:
        if (
            self.kind == "research"
            and self.research_mode not in {"new", "follow_up"}
            or self.kind != "research"
            and self.research_mode != self.kind
        ):
            raise ValueError("research_mode_mismatch")
        return self


class ConversationV13(ClosedV9):
    act: Literal[
        "acknowledge",
        "pleased",
        "greet",
        "greet_morning",
        "social",
        "help",
        "clarify",
        "unsupported",
        "explain_previous",
        "simplify_previous",
        "repeat_previous",
    ]
    reason: (
        Literal[
            "needs_criteria",
            "needs_location",
            "needs_date",
            "needs_definition",
            "needs_context",
            "outside_research",
            "unsupported_constraint",
            "insufficient_structured_data",
        ]
        | None
    )

    @model_validator(mode="after")
    def reason_matches_act(self) -> Self:
        if self.act == "clarify":
            valid = self.reason in {
                "needs_criteria",
                "needs_location",
                "needs_date",
                "needs_definition",
                "needs_context",
            }
        elif self.act == "unsupported":
            valid = self.reason in {
                "outside_research",
                "unsupported_constraint",
                "insufficient_structured_data",
            }
        else:
            valid = self.reason is None
        if not valid:
            raise ValueError("conversation_reason_mismatch")
        return self


class ConversationInteractionV13(ClosedV9):
    kind: Literal[
        "acknowledgement",
        "greeting",
        "social",
        "help",
        "correction",
        "clarification_response",
        "clarification",
    ]
    conversation: ConversationV13

    @model_validator(mode="after")
    def act_matches_kind(self) -> Self:
        allowed = {
            "acknowledgement": {"acknowledge", "pleased"},
            "greeting": {"greet", "greet_morning"},
            "social": {"social", "explain_previous", "simplify_previous", "repeat_previous"},
            "help": {"help"},
            "correction": {"clarify", "unsupported"},
            "clarification_response": {"clarify", "unsupported"},
            "clarification": {"clarify", "unsupported"},
        }
        if self.conversation.act not in allowed[self.kind]:
            raise ValueError("interaction_act_mismatch")
        return self


InteractionV13 = ResearchInteractionV13 | ConversationInteractionV13


class ResearchQueryPlanV13(ClosedV9):
    original_query: QueryV9
    language: AnswerLanguage
    interaction: InteractionV13

    @model_validator(mode="after")
    def exact_query(self, info: ValidationInfo) -> Self:
        if info.context is not None and self.original_query != info.context["original_query"]:
            raise ValueError("original_query_changed")
        if (
            isinstance(self.interaction, ResearchInteractionV13)
            and self.interaction.research_plan.original_query != self.original_query
        ):
            raise ValueError("nested_original_query_changed")
        return self


class DiagnosticsV13(ClosedV9):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    interaction_kind: InteractionKind
    validation_stage: Literal["validated"]
    planner_model: NameV9
    planner_prompt_version: Literal["research-planner-v19"]
    planner_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)


class PlanResponseV13(ClosedV9):
    schema_version: Literal["research-query-plan-v13"]
    prompt_version: Literal["research-planner-v19"]
    model: NameV9
    plan: ResearchQueryPlanV13
    reference_date: date
    timezone: str = Field(max_length=64)
    diagnostics: DiagnosticsV13

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if (
            self.diagnostics.interaction_kind != self.plan.interaction.kind
            or self.diagnostics.planner_model != self.model
            or self.diagnostics.planner_prompt_version != self.prompt_version
        ):
            raise ValueError("envelope_disposition_mismatch")
        return self
