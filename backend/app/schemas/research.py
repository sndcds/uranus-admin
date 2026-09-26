"""Research-only contracts. No workflow, account, actor or private contact fields."""

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.finding import Pagination

ResearchType = Literal["event", "venue", "organization"]
ResearchStatus = Literal["released", "cancelled", "deferred", "rescheduled"]


class ResearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    q: str = Field(default="", max_length=120)
    entity_type: Literal["all", "event", "venue", "organization"] = "all"
    from_date: date | None = None
    to_date: date | None = None
    city: str = Field(default="", max_length=100)
    category: int | None = Field(default=None, ge=0, le=2147483647)
    status: ResearchStatus | None = None
    organization_id: UUID | None = None
    venue_id: UUID | None = None
    sort: Literal["date", "name"] = "date"
    page: int = Field(default=1, ge=1, le=100_000)
    page_size: int = Field(default=25, ge=1, le=100)

    @model_validator(mode="after")
    def ordered_dates(self) -> "ResearchFilters":
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("Date range must be ordered")
        return self


class ResearchCategory(BaseModel):
    id: int
    name: str


class ResearchLocation(BaseModel):
    latitude: float
    longitude: float


class ResearchRecord(BaseModel):
    entity_type: ResearchType
    entity_key: UUID
    name: str
    description: str | None = None
    status: ResearchStatus | None = None
    categories: list[ResearchCategory] = Field(default_factory=list)
    language: str | None = None
    start_date: date | None = None
    start_time: time | None = None
    end_date: date | None = None
    end_time: time | None = None
    all_day: bool | None = None
    organization_id: UUID | None = None
    organization_name: str | None = None
    venue_id: UUID | None = None
    venue_name: str | None = None
    space_id: UUID | None = None
    space_name: str | None = None
    city: str | None = None
    address: str | None = None
    location: ResearchLocation | None = None
    event_count: int | None = None
    source_url: str | None = None
    image_url: str | None = None
    created_at: datetime | None = None
    modified_at: datetime | None = None


class ResearchPage(BaseModel):
    items: list[ResearchRecord]
    pagination: Pagination
    observed_at: datetime
    timezone: str


class ResearchDate(BaseModel):
    id: UUID
    start_date: date
    start_time: time | None
    end_date: date | None
    end_time: time | None
    all_day: bool | None
    status: ResearchStatus
    venue_id: UUID | None
    venue_name: str | None
    space_id: UUID | None
    space_name: str | None
    city: str | None
    address: str | None
    location: ResearchLocation | None


class ResearchDates(BaseModel):
    items: list[ResearchDate]
    pagination: Pagination


class ResearchMonth(BaseModel):
    month: date
    event_count: int


class ResearchUsageItem(BaseModel):
    kind: Literal["venue", "organization", "category"]
    key: str
    name: str
    event_count: int


class ResearchDetail(BaseModel):
    item: ResearchRecord
    events: ResearchPage
    dates: ResearchDates
    months: list[ResearchMonth]
    usage: list[ResearchUsageItem]
    observed_at: datetime


class ResearchExport(BaseModel):
    columns: list[str]
    rows: list[dict[str, str | None]]
    total: int
    observed_at: datetime


class ResearchOptions(BaseModel):
    categories: list[ResearchCategory]
