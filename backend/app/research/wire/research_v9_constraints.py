"""Closed v9 temporal, spatial, relation and interpretation constraints; no execution."""

from datetime import date, time
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.research.wire.research_v9_types import (
    ClosedV9,
    CountV9,
    CurrencyV9,
    DimensionV9,
    LocalTimeV9,
    NameV9,
    QueryV9,
    TopicV9,
)


class TemporalV9(ClosedV9):
    field: Literal["start_date", "created_at", "modified_at"]
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
    before_time: LocalTimeV9 | None
    after_time: LocalTimeV9 | None
    weekday: (
        Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] | None
    )
    calendar_relation: Literal["none", "holiday", "school_holiday"]
    calendar_area_query: NameV9 | None
    overlap: bool
    multi_day: bool
    lookback: Annotated[int, Field(ge=1, le=120)] | None
    lookback_unit: Literal["day", "week", "month", "year"] | None

    @model_validator(mode="after")
    def temporal_consistency(self) -> Self:
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
            self.time_of_day != "none"
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


class SpatialV9(ClosedV9):
    relation: Literal[
        "at",
        "inside",
        "outside",
        "nearby",
        "within_radius",
        "near_border",
        "across_border",
        "north_of",
        "south_of",
        "east_of",
        "west_of",
        "nearest",
    ]
    place_query: NameV9 | None
    area_query: NameV9 | None
    radius_m: Annotated[int, Field(ge=1, le=500_000)] | None
    reference: Literal["named", "user_location", "border", "nearest_venue"]

    @model_validator(mode="after")
    def geography(self) -> Self:
        if self.place_query is not None and self.area_query is not None:
            raise ValueError("conflicting_geography_slots")
        if self.radius_m is not None and self.relation not in {"within_radius", "near_border"}:
            raise ValueError("radius_relation_mismatch")
        if self.relation == "within_radius" and self.radius_m is None:
            raise ValueError("radius_required")
        if self.relation == "nearby":
            if (
                self.reference != "user_location"
                or self.place_query is not None
                or self.area_query is not None
            ):
                raise ValueError("nearby_requires_deictic_reference_only")
        elif self.reference == "user_location":
            if self.place_query is not None or self.area_query is not None:
                raise ValueError("deictic_reference_cannot_have_named_slots")
            if self.relation not in {"within_radius", "nearest"}:
                raise ValueError("invalid_deictic_relation")
        if self.relation in {"near_border", "across_border"} and self.reference != "border":
            raise ValueError("border_reference_required")
        if self.reference == "border" and self.relation not in {
            "near_border",
            "across_border",
            "nearest",
        }:
            raise ValueError("invalid_border_relation")
        if self.reference == "nearest_venue" and (
            self.relation != "nearest"
            or self.area_query is not None
            or self.place_query is not None
        ):
            raise ValueError("invalid_nearest_venue_reference")
        if self.relation == "at" and self.area_query is not None:
            raise ValueError("named_place_requires_place_slot")
        if self.relation in {"inside", "outside"} and self.place_query is not None:
            # Named places use spatial direction/distance; membership needs an area.
            raise ValueError("membership_requires_area")
        return self


class PriceV9(ClosedV9):
    mode: Literal["free", "paid", "less_than", "greater_than", "between"]
    minimum: Annotated[float, Field(ge=0, le=1_000_000)] | None
    maximum: Annotated[float, Field(ge=0, le=1_000_000)] | None
    currency: CurrencyV9 | None

    @model_validator(mode="after")
    def bounds(self) -> Self:
        if self.mode in {"free", "paid"}:
            if self.minimum is not None or self.maximum is not None:
                raise ValueError("free_paid_have_no_numeric_bounds")
        else:
            if self.currency is None:
                raise ValueError("numeric_price_requires_currency")
            if self.mode == "less_than" and (self.maximum is None or self.minimum is not None):
                raise ValueError("less_than_requires_maximum_only")
            if self.mode == "greater_than" and (self.minimum is None or self.maximum is not None):
                raise ValueError("greater_than_requires_minimum_only")
            if self.mode == "between" and (
                self.minimum is None or self.maximum is None or self.maximum < self.minimum
            ):
                raise ValueError("between_requires_ordered_price_bounds")
        return self


class SemanticV9(ClosedV9):
    query: TopicV9
    focus: TopicV9 | None


class ComparisonTargetV9(ClosedV9):
    kind: DimensionV9
    query: NameV9


# Undirected declarative domain edges, not database joins. Derived paths must be explicit.
RELATION_EDGES = frozenset(
    frozenset(pair)
    for pair in (
        ("organization", "event"),
        ("event", "occurrence"),
        ("event", "venue"),
        ("event", "space"),
        ("space", "venue"),
        ("event", "category"),
        ("event", "event_type"),
        ("event", "genre"),
    )
)
RelationNodeV9 = Literal[
    "organization", "event", "occurrence", "venue", "space", "category", "event_type", "genre"
]


class RelationV9(ClosedV9):
    operation: Literal["related", "shared", "path", "distinct_count"]
    source: RelationNodeV9
    target: RelationNodeV9
    via: list[RelationNodeV9] = Field(max_length=3)
    source_query: NameV9 | None
    target_query: NameV9 | None

    @model_validator(mode="after")
    def closed_path(self) -> Self:
        path = [self.source, *self.via, self.target]
        if any(
            frozenset((a, b)) not in RELATION_EDGES for a, b in zip(path, path[1:], strict=False)
        ):
            raise ValueError("unknown_relation_edge")
        if self.operation == "shared" and (self.source != self.target or not self.via):
            raise ValueError("shared_requires_same_entity_via_related_entities")
        return self


class TrendV9(ClosedV9):
    measure: Literal["event_count", "occurrence_count", "venue_count", "organization_count"]
    comparison: Literal["previous_period", "previous_year"]
    window: Literal["day", "week", "month", "quarter", "year"]
    change: Literal["absolute_change", "percentage_change"]


class AnomalyV9(ClosedV9):
    kind: Literal["rare", "inactive", "outlier"]
    measure: CountV9 | None
    # No implicit statistical algorithm; criteria must be supplied or clarified.


class ExplainV9(ClosedV9):
    target: Literal["result", "metric", "filter", "population", "source", "definition", "exclusion"]
    term: NameV9 | None
    context: Literal["previous_result", "definition"]

    @model_validator(mode="after")
    def definition_term(self) -> Self:
        if self.context == "definition" and (self.target != "definition" or self.term is None):
            raise ValueError("definition_requires_term")
        return self


class KnowledgeV9(ClosedV9):
    query: QueryV9
