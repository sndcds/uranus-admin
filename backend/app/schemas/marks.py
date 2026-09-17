"""Independent, human-authored concerns about source records."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, computed_field, model_validator

from app.schemas.action import Action
from app.schemas.activity import EntityType
from app.schemas.finding import Pagination

MarkEntityType = EntityType | Literal["event_link", "license", "image_link"]
MarkReason = Literal[
    "questionable_content",
    "low_quality",
    "incorrect",
    "incomplete",
    "outdated",
    "duplicate",
    "spam",
    "unsuitable",
    "rights_privacy",
    "technical",
    "other",
]
MarkStatus = Literal["open", "in_progress", "done"]
Urgency = Literal["normal", "high", "urgent"]


class MarkFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reasons: list[MarkReason] = Field(min_length=1, max_length=11)
    reason_detail: str | None = Field(default=None, min_length=1, max_length=2000)
    urgency: Urgency = "normal"

    @model_validator(mode="after")
    def valid_reasons(self) -> "MarkFields":
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("Reasons must be unique")
        if "other" in self.reasons and not self.reason_detail:
            raise ValueError("Other requires an explanation")
        return self


class MarkCreate(MarkFields):
    entity_type: MarkEntityType
    entity_key: str = Field(min_length=1, max_length=1024)
    note: str | None = Field(default=None, min_length=1, max_length=4000)


class MarkUpdate(MarkFields):
    # Full workflow state plus an optional new note. Existing notes are never replaced.
    version: int = Field(ge=1)
    status: MarkStatus
    note: str | None = Field(default=None, min_length=1, max_length=4000)


class Mark(BaseModel):
    id: UUID
    entity_type: MarkEntityType
    entity_key: str
    entity_name: str
    reasons: list[MarkReason]
    reason_detail: str | None
    urgency: Urgency
    status: MarkStatus
    version: int
    created_at: AwareDatetime
    created_by: str
    updated_at: AwareDatetime
    completed_at: AwareDatetime | None
    completed_by: str | None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def action(self) -> Action | None:
        if self.entity_type in {"event", "venue", "space", "organization", "user", "image"}:
            return Action.model_validate(
                {
                    "route": "activity",
                    "entity_type": self.entity_type,
                    "entity_key": self.entity_key,
                }
            )
        return None


class MarkEvent(BaseModel):
    id: UUID
    version: int
    kind: Literal["created", "updated", "completed", "reopened"]
    author: str
    created_at: AwareDatetime
    note: str | None
    status: MarkStatus
    reasons: list[MarkReason]
    reason_detail: str | None
    urgency: Urgency


class MarkDetail(Mark):
    events: list[MarkEvent]


class MarkPage(BaseModel):
    items: list[Mark]
    pagination: Pagination


class MarkFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: MarkEntityType | None = None
    entity_key: str | None = Field(default=None, min_length=1, max_length=1024)
    status: Literal["active", "open", "in_progress", "done", "all"] = "active"
    urgency: Urgency | None = None
    reason: MarkReason | None = None
    sort: Literal["urgency", "newest"] = "urgency"
    page: int = Field(default=1, ge=1, le=100_000)
    page_size: int = Field(default=50, ge=1, le=100)
