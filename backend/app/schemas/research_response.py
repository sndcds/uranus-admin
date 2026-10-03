"""HTTP response composition. Planner provenance remains at the API boundary."""

from datetime import datetime

from pydantic import Field

from app.schemas.research_analytics import AnalyticalPlanResponse
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
    sql_provenance: ResearchSqlStatements
    query: Query
    plan: GeographicPlanResponse | PlanResponse | AnalyticalPlanResponse
    resolution: list[ResolvedField] = Field(default_factory=list, max_length=32)
    result: ExecutionResult
    execution: ExecutionProvenance
    observed_at: datetime
    timezone: str
    diagnostics: ExecutionDiagnostics
