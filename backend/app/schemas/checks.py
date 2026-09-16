from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.schemas.finding import Pagination


class CheckRun(BaseModel):
    id: UUID
    started_at: datetime
    finished_at: datetime | None
    status: Literal["queued", "running", "success", "failed"]
    rule_count: int
    finding_count: int
    error_message: str | None
    rule_results: dict[str, Any]


class CheckRunPage(BaseModel):
    items: list[CheckRun]
    pagination: Pagination


class ReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finding_id: str = Field(min_length=1, max_length=8192)
    status: Literal["open", "in_progress", "snoozed", "exception"]
    assigned_to: UUID | None = None
    snoozed_until: AwareDatetime | None = None
    comment: str | None = Field(default=None, max_length=4000)
    exception_reason: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def consistent_state(self) -> "ReviewUpdate":
        if self.status == "snoozed" and self.snoozed_until is None:
            raise ValueError("Snoozed findings require an expiry")
        if self.status == "exception" and not (
            self.exception_reason and self.exception_reason.strip()
        ):
            raise ValueError("Exceptions require a reason")
        return self
