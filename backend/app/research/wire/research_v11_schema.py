"""Additive conversation wire boundary; v10 stays frozen."""

from datetime import date
from typing import Literal, Self

from pydantic import Field, model_validator

from app.research.wire.research_v9_types import ClosedV9, IntentV9, NameV9
from app.research.wire.research_v10_schema import ResearchQueryPlanV10


class ResearchQueryPlanV11(ResearchQueryPlanV10):
    pass


class DiagnosticsV11(ClosedV9):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    planner_intent: IntentV9
    planner_model: NameV9
    planner_prompt_version: Literal["research-planner-v17"]
    planner_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)


class PlanResponseV11(ClosedV9):
    kind: Literal["plan", "needs_clarification", "unsupported"]
    schema_version: Literal["research-query-plan-v11"]
    prompt_version: Literal["research-planner-v17"]
    model: NameV9
    plan: ResearchQueryPlanV11
    reference_date: date
    timezone: str = Field(max_length=64)
    diagnostics: DiagnosticsV11

    @model_validator(mode="after")
    def disposition(self) -> Self:
        expected = (
            "unsupported"
            if self.plan.unsupported_reason is not None
            else "needs_clarification"
            if self.plan.clarification != "none"
            else "plan"
        )
        if (
            self.kind != expected
            or self.diagnostics.planner_intent != self.plan.intent
            or self.diagnostics.planner_model != self.model
            or self.diagnostics.planner_prompt_version != self.prompt_version
        ):
            raise ValueError("envelope_disposition_mismatch")
        return self
