"""Research-only contracts. No workflow, account, actor or private contact fields."""

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.research.area_selection import MAX_AREA_IDS, normalize_area_ids
from app.research.chunk_kinds import Kind
from app.schemas.finding import Pagination
from app.schemas.genre import GenreKey

ResearchType = Literal["event", "venue", "organization"]
ResearchStatus = Literal["released", "cancelled", "deferred", "rescheduled"]


class ResearchFilterFields(BaseModel):
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
    area_id: UUID | None = None
    page: int = Field(default=1, ge=1, le=100_000)
    page_size: int = Field(default=25, ge=1, le=100)

    @model_validator(mode="after")
    def ordered_dates(self) -> "ResearchFilterFields":
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("Date range must be ordered")
        return self


class ResearchFilters(ResearchFilterFields):
    sort: Literal["date", "name"] = "date"


class SemanticResearchFilters(ResearchFilterFields):
    area_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=MAX_AREA_IDS)

    q: str = Field(min_length=2, max_length=120, pattern=r"\S.*\S")
    entity_type: Literal["event"] = "event"
    page: int = Field(default=1, ge=1, le=1)
    page_size: int = Field(default=20, ge=1, le=20)
    genre_keys: list[GenreKey] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def structured_filters(self) -> "SemanticResearchFilters":
        self.genre_keys = sorted(set(self.genre_keys))
        return self

    @model_validator(mode="after")
    def selected_areas(self) -> "SemanticResearchFilters":
        selected = normalize_area_ids(self.area_id, self.area_ids)
        if self.area_ids is not None:
            self.area_ids = selected
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


class SemanticEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Kind
    label: str
    text: str = Field(min_length=1, max_length=200_000)


class SemanticExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    score: float
    matched_aspect: Kind
    matched_aspect_label: str
    reason: str
    evidence: SemanticEvidence
    supporting_evidence: list[SemanticEvidence] = Field(max_length=3)


class SemanticResearchRecord(ResearchRecord):
    model_config = ConfigDict(extra="forbid")

    semantic: SemanticExplanation


class SemanticResearchPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SemanticResearchRecord] = Field(max_length=20)
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
