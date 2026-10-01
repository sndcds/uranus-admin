"""Domain contract v4; compatible addition beside the existing v3 endpoint."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

FactKey = Literal[
    "uranus_overview",
    "admin_overview",
    "semantic_search_repository",
    "embedding_component",
    "embedding_model",
    "qdrant_usage",
    "encoder_communication",
    "planner_component",
    "geocoding",
    "architecture",
    "founding_date",
    "unknown",
]
METRICS = {
    "event": (
        "description_characters",
        "description_words",
        "public_text_characters",
        "occurrence_count",
        "duration_minutes",
    ),
    "venue": ("event_count", "occurrence_count", "organization_count", "category_count"),
    "organization": (
        "event_count",
        "occurrence_count",
        "venue_count",
        "area_count",
        "category_count",
    ),
    "area": ("event_count", "venue_count", "organization_count", "events_per_capita"),
    "category": ("event_count",),
}
EXECUTABLE = {
    ("event", "description_characters"),
    ("event", "occurrence_count"),
    ("organization", "event_count"),
    ("organization", "venue_count"),
    ("venue", "occurrence_count"),
    ("category", "event_count"),
}


class ClosedV4(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class DataPlan(ClosedV4):
    domain: Literal["data"] = "data"
    operation: Literal["rank"] = "rank"
    entity_type: Literal["event", "venue", "organization", "category", "area"]
    metric: Literal[
        "description_characters",
        "description_words",
        "public_text_characters",
        "occurrence_count",
        "duration_minutes",
        "event_count",
        "organization_count",
        "category_count",
        "venue_count",
        "area_count",
        "events_per_capita",
    ]
    ordering: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=1, ge=1, le=20)
    area_query: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def compatible(self) -> Self:
        if (self.entity_type, self.metric) not in EXECUTABLE:
            raise ValueError("unsupported_metric")
        if self.area_query is not None and not self.area_query.strip():
            raise ValueError("blank_area")
        return self


class KnowledgePlan(ClosedV4):
    domain: Literal["project_knowledge"] = "project_knowledge"
    operation: Literal["evidence_answer"] = "evidence_answer"
    knowledge_query: str = Field(min_length=1, max_length=2000)
    fact: FactKey
    answer_mode: Literal["evidence"] = "evidence"


PlanV4 = Annotated[DataPlan | KnowledgePlan, Field(discriminator="domain")]


class PlanEnvelopeV4(ClosedV4):
    schema_version: Literal["research-query-plan-v4"] = "research-query-plan-v4"
    interpreter_version: Literal["reviewed-catalogue-v1"] = "reviewed-catalogue-v1"
    original_query: str = Field(min_length=1, max_length=2000)
    plan: PlanV4
