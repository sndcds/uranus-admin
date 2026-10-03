"""HTTP response composition. Planner provenance remains at the API boundary."""

from datetime import datetime

from pydantic import Field

from app.research.answer import ANSWER_TEXT_MAX_LENGTH
from app.research.wire.research_v9_schema import PlanResponseV9
from app.research.wire.research_v10_schema import PlanResponseV10
from app.research.wire.research_v11_schema import PlanResponseV11
from app.schemas.research_analytics import AnalyticalPlanResponse
from app.schemas.research_conversation import ResearchPlanSummary
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
    answer_text: str | None = Field(max_length=ANSWER_TEXT_MAX_LENGTH)
    conversation_summary: ResearchPlanSummary | None = None
    sql_provenance: ResearchSqlStatements = Field(default_factory=list)
    query: Query
    plan: (
        GeographicPlanResponse
        | PlanResponse
        | AnalyticalPlanResponse
        | PlanResponseV9
        | PlanResponseV10
        | PlanResponseV11
    )
    resolution: list[ResolvedField] = Field(default_factory=list, max_length=32)
    result: ExecutionResult
    execution: ExecutionProvenance
    observed_at: datetime
    timezone: str
    diagnostics: ExecutionDiagnostics
