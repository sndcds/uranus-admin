"""HTTP response composition. Planner provenance remains at the API boundary."""

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from app.research.answer import ANSWER_TEXT_MAX_LENGTH
from app.research.wire.research_v9_schema import PlanResponseV9
from app.research.wire.research_v10_schema import PlanResponseV10
from app.research.wire.research_v11_schema import PlanResponseV11
from app.research.wire.research_v12_schema import PlanResponseV12
from app.research.wire.research_v13_schema import (
    AnswerLanguage,
    ConversationInteractionV13,
    PlanResponseV13,
    ResearchInteractionV13,
)
from app.schemas.research_analytics import AnalyticalPlanResponse
from app.schemas.research_conversation import ResearchPlanSummary
from app.schemas.research_conversation_v12 import ResearchPlanSummaryV12
from app.schemas.research_execution import (
    ExecutionDiagnostics,
    ExecutionProvenance,
    ExecutionResult,
    ResolvedField,
)
from app.schemas.research_geography import GeographicPlanResponse
from app.schemas.research_planner import PlanResponse
from app.schemas.research_sql import ResearchSqlStatements
from app.schemas.research_values import ClosedModel, Query


class ResearchExecutionResponse(ClosedModel):
    conversation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{43}$")
    language: AnswerLanguage | None = None
    answer_text: str | None = Field(max_length=ANSWER_TEXT_MAX_LENGTH)
    conversation_summary: ResearchPlanSummaryV12 | ResearchPlanSummary | None = None
    sql_provenance: ResearchSqlStatements = Field(default_factory=list)
    query: Query
    plan: (
        GeographicPlanResponse
        | PlanResponse
        | AnalyticalPlanResponse
        | PlanResponseV9
        | PlanResponseV10
        | PlanResponseV11
        | PlanResponseV12
        | PlanResponseV13
    )
    resolution: list[ResolvedField] = Field(default_factory=list, max_length=32)
    result: ExecutionResult
    execution: ExecutionProvenance
    observed_at: datetime
    timezone: str
    diagnostics: ExecutionDiagnostics

    @model_validator(mode="after")
    def v13_execution_boundary(self) -> Self:
        if isinstance(self.plan, PlanResponseV13) and (
            not isinstance(self.plan.plan.interaction, ResearchInteractionV13)
            or self.conversation_summary is not None
            or self.conversation_id is None
            or self.language != self.plan.plan.language
            or self.query != self.plan.plan.original_query
        ):
            raise ValueError("invalid_conversational_execution_response")
        return self


class ConversationResponse(ClosedModel):
    kind: Literal["conversation"] = "conversation"
    answer_text: str = Field(min_length=1, max_length=ANSWER_TEXT_MAX_LENGTH)
    language: AnswerLanguage
    conversation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    interaction: ConversationInteractionV13
