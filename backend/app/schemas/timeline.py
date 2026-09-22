"""Bounded entity timeline contracts assembled from verified source/admin timestamps."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.cursor import CursorPagination
from app.schemas.finding import Severity

TimelineEntityType = Literal["event", "organization", "venue", "space", "user", "image"]
TimelineKind = Literal[
    "source_created",
    "source_updated",
    "finding_detected",
    "finding_reviewed",
    "finding_reopened",
    "finding_resolved",
    "mark_created",
    "mark_updated",
    "mark_completed",
    "mark_reopened",
    "notification_delivery",
    "url_check",
    "geocode_request",
    "geocode_result",
    "team_invitation",
    "partner_request",
]


class TimelineFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cursor: str | None = Field(default=None, max_length=16384)
    page_size: int = Field(default=25, ge=1, le=50)


class TimelineMetadata(BaseModel):
    status: str | None = Field(default=None, max_length=64)
    severity: Severity | None = None
    rule: str | None = Field(default=None, max_length=100)
    field: str | None = Field(default=None, max_length=200)
    resource_id: str | None = Field(default=None, max_length=8192)
    generation: int | None = Field(default=None, ge=1)
    score: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    http_status: int | None = Field(default=None, ge=100, le=599)


class TimelineItem(BaseModel):
    id: str = Field(min_length=1, max_length=4096)
    kind: TimelineKind
    occurred_at: AwareDatetime
    title: str = Field(min_length=1, max_length=200)
    summary: str | None = Field(default=None, max_length=5000)
    actor: str | None = Field(default=None, max_length=256)
    href: str | None = Field(default=None, max_length=4096, pattern=r"^/[A-Za-z0-9/?&=._%:-]+$")
    metadata: TimelineMetadata = Field(default_factory=TimelineMetadata)


class TimelinePage(BaseModel):
    entity_type: TimelineEntityType
    entity_key: str
    items: list[TimelineItem] = Field(max_length=50)
    cursor_pagination: CursorPagination
    observed_at: AwareDatetime
