"""Bounded, closed, display-only provenance for authoritative Research source SQL."""

from typing import Annotated, Literal

from pydantic import Field

from app.schemas.research_values import ClosedModel

ResearchSqlKind = Literal["execution", "eligibility", "rehydration", "comparison"]
MAX_SQL_NUMBER = 9_007_199_254_740_991
SqlNumber = (
    Annotated[int, Field(ge=-MAX_SQL_NUMBER, le=MAX_SQL_NUMBER)]
    | Annotated[float, Field(ge=-MAX_SQL_NUMBER, le=MAX_SQL_NUMBER)]
)
SqlScalar = Annotated[str, Field(max_length=4096)] | bool | SqlNumber | None
SqlValue = SqlScalar | Annotated[list[SqlScalar], Field(max_length=100)]
SqlParameters = Annotated[
    dict[Annotated[str, Field(min_length=1, max_length=64)], SqlValue], Field(max_length=64)
]


class ResearchSqlStatement(ClosedModel):
    label: str = Field(min_length=1, max_length=200)
    kind: ResearchSqlKind
    sql: str = Field(min_length=1, max_length=65536)
    parameters: SqlParameters


ResearchSqlStatements = Annotated[list[ResearchSqlStatement], Field(max_length=16)]
