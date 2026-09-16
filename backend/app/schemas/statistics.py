from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.schemas.action import Action

StatisticsPeriod = Literal["24h", "7d", "30d", "90d", "custom"]
StatisticsInterval = Literal["15m", "1h", "6h", "1d"]
StatisticsEntity = Literal[
    "user", "organization", "event", "venue", "space", "partner_request", "team_invitation"
]


class StatisticsFilters(BaseModel):
    model_config = {"extra": "forbid"}
    period: StatisticsPeriod | None = None
    interval: Literal["auto", "15m", "1h", "6h", "1d"] = "auto"
    compare: Literal["previous"] | None = None
    from_at: AwareDatetime | None = None
    to_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def valid_range(self) -> "StatisticsFilters":
        if self.from_at is not None or self.to_at is not None or self.period == "custom":
            if self.period not in (None, "custom") or not (self.from_at and self.to_at):
                raise ValueError("Custom ranges require both boundaries and no preset")
            duration = self.to_at.astimezone(UTC) - self.from_at.astimezone(UTC)
            if not timedelta(0) < duration <= timedelta(days=365):
                raise ValueError("Range must be positive and at most 365 days")
        return self


class EntityTimePoint(BaseModel):
    start_at: datetime
    end_at: datetime
    count: int = Field(ge=0)


class EntityTimeSeries(BaseModel):
    entity_type: StatisticsEntity
    label: str
    total: int = Field(ge=0)
    previous_total: int | None = Field(default=None, ge=0)
    points: list[EntityTimePoint]


class RecentEntity(BaseModel):
    entity_type: StatisticsEntity
    entity_key: str
    entity_name: str
    organization_name: str | None
    created_at: datetime
    action: Action


class EntityStatisticsResponse(BaseModel):
    period: StatisticsPeriod
    from_at: datetime
    to_at: datetime
    timezone: str
    interval: StatisticsInterval
    observed_at: datetime
    previous_from_at: datetime | None = None
    previous_to_at: datetime | None = None
    series: list[EntityTimeSeries]
    recent: list[RecentEntity]
