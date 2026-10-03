"""Public administrative selection results, independent of internal plan types."""

from typing import Literal

from pydantic import Field

from app.schemas.research import ResearchRecord
from app.schemas.research_sql import ResearchSqlStatements
from app.schemas.research_values import ClosedModel

AdministrativeLevel = Literal["country", "state", "district", "municipality", "region"]


class AdministrativeGroup(ClosedModel):
    area_id: str
    name: str
    level: AdministrativeLevel
    event_count: int = Field(ge=0)


class AdministrativeResult(ClosedModel):
    sql_provenance: ResearchSqlStatements = Field(default_factory=list)
    kind: Literal["records", "count", "groups"]
    records: list[ResearchRecord] = Field(default_factory=list, max_length=20)
    groups: list[AdministrativeGroup] = Field(default_factory=list, max_length=20)
    count: int | None = Field(default=None, ge=0)
    unknown_location_count: int = Field(ge=0)
    inventory_countries: list[str] = Field(default_factory=list, max_length=250)
