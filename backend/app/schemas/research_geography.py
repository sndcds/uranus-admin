"""Versioned geographic v6/v11 contract; earlier contracts remain frozen."""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.schemas.research_analytics import AnalyticalQueryPlan, ClosedModel, Intent, Slot


class GeographicQueryPlan(AnalyticalQueryPlan):
    place_query: Slot | None
    location_relation: Literal["none", "nearby"]

    @model_validator(mode="after")
    def geographic_consistency(self) -> Self:
        if self.unsupported_reason == "outside_research" and (
            self.place_query is not None or self.location_relation != "none"
        ):
            raise ValueError("outside_research_requires_neutral_geography")
        if self.location_relation == "nearby":
            if (
                self.place_query is not None
                or self.area_query is not None
                or self.venue_query is not None
            ):
                raise ValueError("nearby_requires_location_context_only")
            if self.clarification != "needs_location":
                raise ValueError("nearby_requires_location_clarification")
        elif self.clarification == "needs_location":
            raise ValueError("location_clarification_requires_nearby")
        return self


class GeographicDiagnostics(ClosedModel):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    planner_intent: Intent
    planner_model: str = Field(min_length=1, max_length=160)
    planner_prompt_version: Literal["research-planner-v11"]
    planner_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)


class GeographicEnvelope(ClosedModel):
    schema_version: Literal["research-query-plan-v6"]
    prompt_version: Literal["research-planner-v11"]
    model: str = Field(min_length=1, max_length=160)
    plan: GeographicQueryPlan
    reference_date: date
    timezone: str = Field(max_length=64)
    diagnostics: GeographicDiagnostics


class GeographicResponse(GeographicEnvelope):
    kind: Literal["plan"] = "plan"


class GeographicClarification(GeographicEnvelope):
    kind: Literal["needs_clarification"] = "needs_clarification"


GeographicPlanResponse = Annotated[
    GeographicResponse | GeographicClarification, Field(discriminator="kind")
]
