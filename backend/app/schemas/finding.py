from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


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
    entity_type: str
    entity_id: UUID
    entity_name: str
    organization_id: UUID
    organization_name: str
    field: str
    message: str
    address: Address
    status: FindingStatus = FindingStatus.open
    first_seen_at: datetime | None = None
    last_seen_at: datetime
    resolved_at: datetime | None = None
    upcoming_event_date_count: int = Field(ge=0)
    upcoming_published_event_date_count: int = Field(ge=0)
    soon_published_event_date_count: int = Field(ge=0)


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
