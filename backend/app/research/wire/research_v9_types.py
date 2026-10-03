"""Independent v9 vocabulary, nonrecursive metrics and typed predicates."""

from datetime import date, time
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    StringConstraints,
    WithJsonSchema,
    model_validator,
)


def nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("blank_string")
    return value


class ClosedV9(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


QueryV9 = Annotated[str, StringConstraints(min_length=1, max_length=2000), AfterValidator(nonblank)]
NameV9 = Annotated[str, StringConstraints(min_length=1, max_length=160), AfterValidator(nonblank)]
TopicV9 = Annotated[str, StringConstraints(min_length=1, max_length=500), AfterValidator(nonblank)]
# JSON Schema's format=time denotes RFC3339 full-time (with an offset), whereas
# v9 validators require local wall clocks. Describe canonical output accurately;
# keep datetime.time parsing and every existing validator unchanged.
LocalTimeV9 = Annotated[
    time,
    WithJsonSchema(
        {
            "type": "string",
            "pattern": r"^([01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9](\.[0-9]{1,6})?$",
            "description": "Local wall-clock time without timezone or UTC offset",
        }
    ),
]
EntityV9 = Literal[
    "event", "occurrence", "venue", "space", "organization", "municipality", "region"
]
IntentV9 = Literal[
    "list",
    "search",
    "count",
    "aggregate",
    "rank",
    "compare",
    "taxonomy",
    "relation",
    "trend",
    "anomaly",
    "explain",
    "knowledge",
]
DimensionV9 = Literal[
    "event",
    "occurrence",
    "venue",
    "space",
    "organization",
    "category",
    "event_type",
    "genre",
    "municipality",
    "region",
    "country",
]
GroupingV9 = Literal[
    "event",
    "occurrence",
    "venue",
    "space",
    "organization",
    "category",
    "event_type",
    "genre",
    "municipality",
    "region",
    "country",
    "hour",
    "weekday",
    "week",
    "month",
    "year",
]
TaxonomyV9 = Literal["category", "event_type", "genre"]
MetricFieldV9 = Literal[
    "description",
    "start_date",
    "start_time",
    "end_date",
    "end_time",
    "created_at",
    "modified_at",
    "min_price",
    "max_price",
    "latitude",
    "longitude",
    "population",
]
CountV9 = Literal[
    "event_count", "occurrence_count", "venue_count", "space_count", "organization_count"
]
CurrencyV9 = Literal["EUR"]
COUNT_OPERATIONS = {
    "event_count",
    "occurrence_count",
    "venue_count",
    "space_count",
    "organization_count",
}


class NumericPredicateV9(ClosedV9):
    operator: Literal["eq", "neq", "lt", "lte", "gt", "gte", "between"]
    value: float
    upper: float | None

    @model_validator(mode="after")
    def interval(self) -> Self:
        if self.operator == "between":
            if self.upper is None or self.upper < self.value:
                raise ValueError("ordered_numeric_bounds_required")
        elif self.upper is not None:
            raise ValueError("upper_requires_between")
        return self


class MetricOperandV9(ClosedV9):
    operation: Literal[
        "event_count",
        "occurrence_count",
        "venue_count",
        "space_count",
        "organization_count",
        "distinct_count",
        "population",
    ]
    distinct_by: DimensionV9 | None
    subset: Literal["all", "free", "paid"]

    @model_validator(mode="after")
    def operand(self) -> Self:
        if (self.operation == "distinct_count") != (self.distinct_by is not None):
            raise ValueError("operand_distinct_dimension_required")
        if self.subset != "all" and self.operation not in {"event_count", "occurrence_count"}:
            raise ValueError("price_subset_requires_events_or_occurrences")
        return self


class MetricV9(ClosedV9):
    operation: Literal[
        "event_count",
        "occurrence_count",
        "venue_count",
        "space_count",
        "organization_count",
        "distinct_count",
        "minimum",
        "maximum",
        "average",
        "median",
        "field_length",
        "value",
        "duration",
        "distance",
        "diversity",
        "ratio",
        "percentage",
        "frequency",
        "regularity",
        "absolute_change",
        "percentage_change",
    ]
    field: MetricFieldV9 | None
    distinct_by: DimensionV9 | None
    numerator: MetricOperandV9 | None
    denominator: MetricOperandV9 | None
    measure: CountV9 | None
    window: Literal["day", "week", "month", "quarter", "year"] | None
    currency: CurrencyV9 | None

    @model_validator(mode="after")
    def operands(self) -> Self:
        op = self.operation
        if (op in {"distinct_count", "diversity"}) != (self.distinct_by is not None):
            raise ValueError("distinct_dimension_required")
        if op == "diversity" and self.distinct_by not in {
            "category",
            "genre",
            "event_type",
            "organization",
            "venue",
        }:
            raise ValueError("undefined_diversity_dimension")
        if op in {"ratio", "percentage"}:
            if self.numerator is None or self.denominator is None:
                raise ValueError("ratio_requires_operands")
            if op == "percentage" and (
                self.numerator.operation != self.denominator.operation
                or self.numerator.distinct_by != self.denominator.distinct_by
                or self.denominator.subset != "all"
                or self.numerator.subset == "all"
            ):
                raise ValueError("percentage_requires_subset_of_same_population")
        elif self.numerator is not None or self.denominator is not None:
            raise ValueError("unexpected_ratio_operands")
        field_ops = {"minimum", "maximum", "average", "median", "field_length", "value"}
        if (op in field_ops) != (self.field is not None):
            raise ValueError("metric_field_required_or_unexpected")
        if op == "field_length" and self.field != "description":
            raise ValueError("field_length_requires_description")
        if op in {"average", "median"} and self.field not in {
            "min_price",
            "max_price",
            "latitude",
            "longitude",
            "population",
        }:
            raise ValueError("numeric_statistic_requires_numeric_field")
        if op in {"minimum", "maximum", "value"} and self.field == "description":
            raise ValueError("text_requires_field_length")
        if (self.field in {"min_price", "max_price"}) != (self.currency is not None):
            raise ValueError("price_metric_requires_single_currency")
        change_ops = {"frequency", "regularity", "absolute_change", "percentage_change"}
        if (op in change_ops) != (self.measure is not None and self.window is not None):
            raise ValueError("measure_and_window_required")
        if op not in change_ops and (self.measure is not None or self.window is not None):
            raise ValueError("unexpected_metric_window")
        return self


class PresenceFilterV9(ClosedV9):
    field: Literal[
        "description",
        "venue",
        "space",
        "organization",
        "category",
        "event_type",
        "genre",
        "price",
        "image",
        "coordinates",
        "start_date",
        "start_time",
        "created_at",
        "modified_at",
        "status",
        "ticket_link",
        "registration_link",
    ]
    operator: Literal["present", "missing"]


class NameFilterV9(ClosedV9):
    field: Literal["venue", "space", "organization", "category", "event_type", "genre"]
    operator: Literal["eq", "neq"]
    value: NameV9


class DescriptionFilterV9(ClosedV9):
    field: Literal["description"]
    operator: Literal["eq", "neq"]
    value: TopicV9


class StatusFilterV9(ClosedV9):
    field: Literal["status"]
    operator: Literal["eq", "neq"]
    value: Literal["released", "cancelled"]


class NumberFilterV9(ClosedV9):
    field: Literal["price", "population"]
    predicate: NumericPredicateV9
    currency: CurrencyV9 | None

    @model_validator(mode="after")
    def numeric_field(self) -> Self:
        if (self.field == "price") != (self.currency is not None):
            raise ValueError("price_filter_requires_currency")
        if self.predicate.value < 0 or (
            self.predicate.upper is not None and self.predicate.upper < 0
        ):
            raise ValueError("negative_price_or_population")
        return self


class DateFilterV9(ClosedV9):
    field: Literal["start_date", "created_at", "modified_at"]
    operator: Literal["eq", "neq", "lt", "lte", "gt", "gte", "between"]
    value: date
    upper: date | None

    @model_validator(mode="after")
    def interval(self) -> Self:
        if self.operator == "between":
            if self.upper is None or self.upper < self.value:
                raise ValueError("ordered_date_bounds_required")
        elif self.upper is not None:
            raise ValueError("upper_requires_between")
        return self


class TimeFilterV9(ClosedV9):
    field: Literal["start_time"]
    operator: Literal["eq", "neq", "lt", "lte", "gt", "gte", "between"]
    value: LocalTimeV9
    upper: LocalTimeV9 | None

    @model_validator(mode="after")
    def interval(self) -> Self:
        if self.value.tzinfo is not None or (
            self.upper is not None and self.upper.tzinfo is not None
        ):
            raise ValueError("local_time_required")
        if self.operator == "between":
            if self.upper is None or self.upper < self.value:
                raise ValueError("ordered_time_bounds_required")
        elif self.upper is not None:
            raise ValueError("upper_requires_between")
        return self


FilterV9 = (
    PresenceFilterV9
    | NameFilterV9
    | DescriptionFilterV9
    | StatusFilterV9
    | NumberFilterV9
    | DateFilterV9
    | TimeFilterV9
)
