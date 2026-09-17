from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.periods import PresetPeriod

EventContentPeriod = PresetPeriod | Literal["all"]
EventReleaseStatus = Literal["released", "draft", "review", "cancelled", "deferred", "rescheduled"]


class EventContentFilters(BaseModel):
    model_config = {"extra": "forbid"}
    period: EventContentPeriod = "24h"
    status: EventReleaseStatus | None = None
    compare: Literal["previous"] | None = None

    @model_validator(mode="after")
    def bounded_comparison(self) -> "EventContentFilters":
        if self.period == "all" and self.compare:
            raise ValueError("All has no previous period")
        return self


class AssignmentCoverage(BaseModel):
    events_with_assignment: int = Field(ge=0)
    events_without_assignment: int = Field(ge=0)
    coverage_percent: float = Field(ge=0, le=100)


class EventContentCoverage(BaseModel):
    categories: AssignmentCoverage
    genres: AssignmentCoverage
    event_types: AssignmentCoverage


class EventContentRankingItem(BaseModel):
    id: str
    name: str
    event_count: int = Field(ge=0)
    event_share_percent: float = Field(ge=0, le=100)
    rank: int = Field(ge=1)
    previous_rank: int | None = None
    rank_delta: int | None = None
    previous_event_count: int | None = None
    count_delta: int | None = None
    previous_share_percent: float | None = None
    share_delta_percentage_points: float | None = None


class EventContentRanking(BaseModel):
    distinct_assignment_count: int = Field(ge=0)
    items: list[EventContentRankingItem] = Field(max_length=10)


class EventContentComparison(BaseModel):
    from_at: datetime
    to_at: datetime
    event_count: int = Field(ge=0)
    coverage: EventContentCoverage


class EventContentStatistics(BaseModel):
    period: EventContentPeriod
    from_at: datetime | None
    to_at: datetime | None
    observed_at: datetime
    timezone: str
    status: EventReleaseStatus | None
    event_count: int = Field(ge=0)
    coverage: EventContentCoverage
    categories: EventContentRanking
    genres: EventContentRanking
    event_types: EventContentRanking
    comparison: EventContentComparison | None
