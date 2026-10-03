"""Bounded advisory semantics, never executable plans or result data."""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Name = Annotated[str, Field(min_length=1, max_length=160)]
Dimension = Literal[
    "event",
    "venue",
    "organization",
    "category",
    "event_type",
    "genre",
    "month",
    "weekday",
    "municipality",
    "district",
    "state",
    "country",
    "region",
]


class ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class ConversationTemporal(ContextModel):
    period: Literal[
        "none",
        "today",
        "tomorrow",
        "this_weekend",
        "next_week",
        "this_month",
        "this_year",
        "past",
        "future",
        "explicit_range",
    ]
    from_date: date | None
    to_date: date | None
    time_of_day: Literal["none", "morning", "afternoon", "evening", "night"]
    weekdays: list[Annotated[int, Field(ge=1, le=7)]] = Field(max_length=7)
    months: list[Annotated[int, Field(ge=1, le=12)]] = Field(max_length=12)

    @field_validator("from_date", "to_date", mode="before")
    @classmethod
    def canonical_date(cls, value: object) -> object:
        # FastAPI validates parsed Python JSON: accept only canonical ISO text,
        # never the coercions (timestamps/compact dates) of a non-strict date field.
        if isinstance(value, str):
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError("canonical_date_required")
            return parsed
        return value

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if len(set(self.weekdays)) != len(self.weekdays) or len(set(self.months)) != len(
            self.months
        ):
            raise ValueError("duplicate_calendar_values")
        if self.period == "explicit_range":
            if self.from_date is None or self.to_date is None or self.from_date > self.to_date:
                raise ValueError("invalid_date_range")
        elif self.from_date is not None or self.to_date is not None:
            raise ValueError("unexpected_dates")
        return self


class ConversationNames(ContextModel):
    venue: Name | None
    organization: Name | None
    event_types: list[Name] = Field(max_length=8)
    categories: list[Name] = Field(max_length=8)
    genres: list[Name] = Field(max_length=8)


class ConversationArea(ContextModel):
    name: Name
    relation: Literal["inside", "outside"]


class ResearchPlanSummary(ContextModel):
    intent: Literal[
        "list", "search", "recommend", "count", "aggregate", "rank", "taxonomy", "spatial_rank"
    ]
    entity_type: Literal["event", "venue", "organization"]
    metric: Literal["none", "event_count", "occurrence_count", "venue_count", "organization_count"]
    groupings: list[Dimension] = Field(max_length=3)
    ordering: Literal["asc", "desc"] | None
    limit: Annotated[int, Field(ge=1, le=20)] | None
    temporal: ConversationTemporal
    filters: ConversationNames
    areas: list[ConversationArea] = Field(max_length=1)
    semantic_query: Name | None
    semantic_focus: Name | None
    taxonomy: Literal["genre", "event_type", "category"] | None
    spatial_metric: Literal["longitude", "latitude"] | None

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if len(set(self.groupings)) != len(self.groupings):
            raise ValueError("duplicate_dimensions")
        if len(self.model_dump_json().encode()) > 2048:
            raise ValueError("summary_too_large")
        return self


class ResearchConversationContext(ContextModel):
    previous_turns: list[ResearchPlanSummary] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if len(self.model_dump_json().encode()) > 8192:
            raise ValueError("context_too_large")
        return self
