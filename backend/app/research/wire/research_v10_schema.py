"""Additive recurring-calendar wire contract; v9 remains frozen."""

from datetime import date, time
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.research.wire.research_v9_constraints import TemporalV9
from app.research.wire.research_v9_schema import ResearchQueryPlanV9
from app.research.wire.research_v9_types import ClosedV9, IntentV9, NameV9


class TemporalV10(TemporalV9):
    recurring_weekdays: list[Annotated[int, Field(ge=1, le=7)]] = Field(max_length=7)
    recurring_months: list[Annotated[int, Field(ge=1, le=12)]] = Field(max_length=12)

    @model_validator(mode="after")
    def temporal_consistency(self) -> Self:
        if len(set(self.recurring_weekdays)) != len(self.recurring_weekdays):
            raise ValueError("duplicate_recurring_weekdays")
        if len(set(self.recurring_months)) != len(self.recurring_months):
            raise ValueError("duplicate_recurring_months")
        if self.weekday is not None and self.recurring_weekdays:
            raise ValueError("conflicting_weekday_representations")
        if self.period == "explicit_range":
            if self.from_date is None or self.to_date is None or self.from_date > self.to_date:
                raise ValueError("explicit_range_requires_ordered_dates")
        elif self.from_date is not None or self.to_date is not None:
            raise ValueError("dates_require_explicit_range")
        if (self.lookback is None) != (self.lookback_unit is None):
            raise ValueError("lookback_requires_unit")
        if self.lookback is not None and self.period != "past":
            raise ValueError("lookback_requires_past")
        for value in (self.before_time, self.after_time):
            if value is not None and value.tzinfo is not None:
                raise ValueError("local_time_required")
        if self.before_time is not None and self.after_time is not None:
            if self.after_time >= self.before_time:
                raise ValueError("inconsistent_clock_interval")
        bounds = {"morning": (6, 12), "afternoon": (12, 18), "evening": (18, 22)}
        if self.time_of_day in bounds:
            lower, upper = bounds[self.time_of_day]
            if (self.before_time is not None and self.before_time <= time(lower)) or (
                self.after_time is not None and self.after_time >= time(upper)
            ):
                raise ValueError("time_of_day_conflicts_with_clock_interval")
        if (
            self.time_of_day == "night"
            and self.before_time is not None
            and self.after_time is not None
        ):
            if self.after_time >= time(6) and self.before_time <= time(22):
                raise ValueError("night_conflicts_with_clock_interval")
        if self.calendar_relation == "none" and self.calendar_area_query is not None:
            raise ValueError("calendar_area_requires_calendar_relation")
        occurrence_only = (
            bool(self.recurring_weekdays)
            or bool(self.recurring_months)
            or self.time_of_day != "none"
            or self.before_time is not None
            or self.after_time is not None
            or self.weekday is not None
            or self.calendar_relation != "none"
            or self.overlap
            or self.multi_day
        )
        if self.field != "start_date" and occurrence_only:
            raise ValueError("occurrence_constraint_on_metadata_time")
        if self.period == "none" and not occurrence_only:
            raise ValueError("unused_temporal_must_be_null")
        return self


class ResearchQueryPlanV10(ResearchQueryPlanV9):
    temporal: TemporalV10 | None


class DiagnosticsV10(ClosedV9):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    planner_intent: IntentV9
    planner_model: NameV9
    planner_prompt_version: Literal["research-planner-v16"]
    planner_ms: float = Field(ge=0)
    total_ms: float = Field(ge=0)


class PlanResponseV10(ClosedV9):
    kind: Literal["plan", "needs_clarification", "unsupported"]
    schema_version: Literal["research-query-plan-v10"]
    prompt_version: Literal["research-planner-v16"]
    model: NameV9
    plan: ResearchQueryPlanV10
    reference_date: date
    timezone: str = Field(max_length=64)
    diagnostics: DiagnosticsV10

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
