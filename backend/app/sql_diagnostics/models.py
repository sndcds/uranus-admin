from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class DiagnosticRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_id: str = Field(min_length=1, max_length=8192)


class DiagnosticCheck(BaseModel):
    label: str
    value: bool | None
    left: JsonValue = None
    operator: str | None = None
    right: JsonValue = None


class DiagnosticEvaluation(BaseModel):
    matched: bool | None
    checks: list[DiagnosticCheck]
    message: str
    engine: Literal["Python"] = "Python"


class SqlDiagnosticDefinition(BaseModel):
    recipe_id: str
    title: str
    datasource: Literal["uranus"] = "uranus"
    readonly: Literal[True] = True
    sql: str
    copy_sql: str
    parameters: dict[str, JsonValue]
    explanation: str
    columns: list[str]
    last_seen_at: datetime


class SqlDiagnosticResult(BaseModel):
    recipe_id: str
    columns: list[str]
    rows: list[dict[str, JsonValue]]
    row_count: int
    duration_ms: float
    observed_at: datetime
    evaluation: DiagnosticEvaluation


@dataclass(frozen=True)
class StoredFinding:
    id: str
    rule: str
    entity_type: str
    entity_key: str
    field: str
    last_seen_at: datetime


@dataclass(frozen=True)
class SqlDiagnosticRecipe:
    id: str
    rule: str
    title: str
    sql: str
    result_fields: tuple[str, ...]
    entity_type: str
    fields: tuple[str, ...]
    explanation: str
