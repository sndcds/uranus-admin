"""V12 summaries retain lexical administrative expectations, never resolved identities."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.research.wire.research_v8_types import AdministrativeLevelV8
from app.schemas.research_conversation import (
    ContextModel,
    ConversationNames,
    ConversationTemporal,
    Dimension,
    Name,
)


class ConversationAreaV12(ContextModel):
    name: Name
    relation: Literal["inside", "outside"]
    expected_level: AdministrativeLevelV8 | None


class ResearchPlanSummaryV12(ContextModel):
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
    areas: list[ConversationAreaV12] = Field(max_length=4)
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


class ResearchConversationContextV12(ContextModel):
    previous_turns: list[ResearchPlanSummaryV12] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if len(self.model_dump_json().encode()) > 8192:
            raise ValueError("context_too_large")
        return self
