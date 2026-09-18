from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.schemas.action import Action
from app.schemas.cursor import CursorPagination
from app.schemas.dashboard import Period
from app.schemas.finding import Pagination

EntityType = Literal[
    "organization",
    "venue",
    "space",
    "event",
    "event_date",
    "user",
    "partner_request",
    "team_membership",
    "image",
]


class ActivityFilters(BaseModel):
    creation_basis: Literal["record", "statistics"] = "record"
    entity_type: EntityType | None = None
    entity_key: str | None = Field(default=None, min_length=1, max_length=1024)
    organization_id: UUID | None = None
    period: Period | None = None
    from_at: AwareDatetime | None = None
    to_at: AwareDatetime | None = None
    timestamp_state: Literal["known", "unknown"] = "known"
    cursor: str | None = Field(default=None, max_length=16384)
    page: int = Field(default=1, ge=1, le=100_000)
    page_size: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def valid_window(self) -> "ActivityFilters":
        if self.period and (self.from_at or self.to_at):
            raise ValueError("Choose period or explicit time boundaries")
        if self.timestamp_state == "unknown" and (self.period or self.from_at or self.to_at):
            raise ValueError("Unknown timestamps cannot be filtered by time")
        if self.from_at and self.to_at and self.from_at >= self.to_at:
            raise ValueError("from_at must precede to_at")
        return self


class ActivityLocation(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


class Activity(BaseModel):
    entity_type: EntityType
    entity_key: str
    entity_name: str
    organization_id: UUID | None
    organization_name: str | None
    created_at: datetime | None
    status: str | None
    action: Action | None = None
    image_url: str | None = None
    public_url: str | None = None
    subtitle: str | None = None
    notice: str | None = None
    address: str | None = None
    email: str | None = None
    location: ActivityLocation | None = None


class ActivityPage(BaseModel):
    cursor_pagination: CursorPagination | None = None
    items: list[Activity]
    pagination: Pagination
    observed_at: datetime
    from_at: datetime | None
    to_at: datetime | None
    timestamp_state: Literal["known", "unknown"]
    unknown_timestamp_count: int
