from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field, computed_field

from app.schemas.action import Action


class Severity(StrEnum):
    error = "error"
    warning = "warning"
    info = "info"


class FindingStatus(StrEnum):
    open = "open"
    reviewed = "reviewed"
    ignored = "ignored"
    resolved = "resolved"


class FindingFilters(BaseModel):
    severity: Severity | None = None
    entity_type: str | None = Field(default=None, max_length=64)
    rule: str | None = Field(default=None, max_length=100)
    organization_id: UUID | None = None
    status: FindingStatus | None = None
    page: int = Field(default=1, ge=1, le=100_000)
    page_size: int = Field(default=50, ge=1, le=100)


class Address(BaseModel):
    street: str | None = None
    house_number: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = None


class Finding(BaseModel):
    id: str
    rule: str
    severity: Severity
    priority: int = Field(ge=1, le=6)
    priority_score: int = Field(ge=0)
    priority_reasons: list[str]
    entity_type: str
    entity_key: str = Field(
        min_length=1, max_length=1024, validation_alias=AliasChoices("entity_key", "entity_id")
    )
    entity_name: str
    organization_id: UUID
    organization_name: str
    field: str
    message: str
    action: Action | None = None
    address: Address
    status: FindingStatus = FindingStatus.open
    first_seen_at: datetime | None = None
    last_seen_at: datetime
    resolved_at: datetime | None = None
    upcoming_event_date_count: int = Field(ge=0)
    upcoming_published_event_date_count: int = Field(ge=0)
    soon_published_event_date_count: int = Field(ge=0)

    @computed_field(deprecated="Use entity_key; composite keys have no UUID alias.")  # type: ignore[prop-decorator]
    @property
    def entity_id(self) -> UUID | None:
        try:
            return UUID(self.entity_key)
        except ValueError:
            return None


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class FindingPage(BaseModel):
    items: list[Finding]
    pagination: Pagination
    observed_at: datetime
    mode: Literal["live"] = "live"
