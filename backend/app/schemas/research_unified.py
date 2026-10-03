from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from app.schemas.project_knowledge import AnswerResponse
from app.schemas.research_domain import ClosedV4, DataPlan
from app.schemas.research_execution import ExecutionFilters
from app.schemas.research_sql import ResearchSqlStatements


class MetricRecord(ClosedV4):
    key: str
    name: str
    value: int = Field(ge=0)


class DataAnswer(ClosedV4):
    sql_provenance: ResearchSqlStatements = Field(default_factory=list)
    authoritative_source: Literal["postgresql"] = "postgresql"
    records: list[MetricRecord] = Field(max_length=20)
    metric: DataPlan
    filters: ExecutionFilters
    observed_at: datetime
    projection_version: Literal["research-public-clean-v1"] = "research-public-clean-v1"


UnifiedAnswer = Annotated[DataAnswer | AnswerResponse, Field(discriminator="authoritative_source")]
