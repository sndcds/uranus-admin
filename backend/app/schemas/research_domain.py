"""Public planner v4 mirror; compatible addition beside the existing v3 endpoint.

Verified against sndcds/uranus-research-planner PR #12 at
a95d9917ca2a7240d3aeccfbc0317ec933ddef23 (domain_schema.py and schemas.Query).
Provider-internal DomainProposal is deliberately not part of this contract.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.research_planner import Query

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
    entity_type: Literal["event", "venue", "organization", "category"]
    metric: Literal["description_characters", "occurrence_count", "event_count", "venue_count"]
    ordering: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=1, ge=1, le=20)
    area_query: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def compatible(self) -> Self:
        if (self.entity_type, self.metric) not in EXECUTABLE:
            raise ValueError("unsupported_metric")
        if self.area_query is not None:
            if (self.entity_type, self.metric) != ("organization", "event_count"):
                raise ValueError("unsupported_area_constraint")
            if not self.area_query.strip():
                raise ValueError("blank_area")
        return self


class KnowledgePlan(ClosedV4):
    domain: Literal["project_knowledge"] = "project_knowledge"
    operation: Literal["evidence_answer"] = "evidence_answer"
    knowledge_query: Query
    fact: FactKey
    answer_mode: Literal["evidence"] = "evidence"


PlanV4 = Annotated[DataPlan | KnowledgePlan, Field(discriminator="domain")]


class PlanEnvelopeV4(ClosedV4):
    schema_version: Literal["research-query-plan-v4"] = "research-query-plan-v4"
    interpreter_version: Literal["research-domain-planner-v2"] = "research-domain-planner-v2"
    original_query: str = Field(min_length=1, max_length=2000)
    plan: PlanV4
