"""Answer prose is a pure projection of executed values and explicit ordering."""

from dataclasses import replace
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.research.answer import ANSWER_TEXT_MAX_LENGTH, build_research_answer
from app.research.plan import InternalResearchPlan
from app.schemas.research import ResearchRecord
from app.schemas.research_execution import (
    AggregateItem,
    AggregateResult,
    ComparisonItem,
    ComparisonResult,
    CountResult,
    ExecutionClarification,
    ExecutionProvenance,
    GroupCoordinate,
    GroupedItem,
    GroupedResult,
    RecordsResult,
    ResolutionCandidate,
    SpatialResult,
    TaxonomyResult,
)
from app.schemas.research_response import ResearchExecutionResponse

PLAN = InternalResearchPlan(intent="aggregate", entity_type="event", ordering="desc")
PROVENANCE = ExecutionProvenance(structured=True)


def answer(result, *, ordering="desc", entity="event", semantic=False):
    return build_research_answer(
        replace(PLAN, ordering=ordering, entity_type=entity),
        result,
        ExecutionProvenance(structured=True, semantic=semantic),
    )


def records(size=2, total=None):
    return RecordsResult(
        items=[
            ResearchRecord(entity_type="event", entity_key=UUID(int=i + 1), name=f"Event {i}")
            for i in range(size)
        ],
        total=total,
    )


def aggregate(values=(7, 2), names=("Konzert", "Lesung")):
    return AggregateResult(
        metric="occurrence_count",
        group_by="event_type",
        items=[
            AggregateItem(key=str(i), name=name, value=value)
            for i, (name, value) in enumerate(zip(names, values, strict=True))
        ],
    )


def grouped(ordering="desc", values=(7, 2), month="09", weekday="7"):
    return GroupedResult(
        metric="occurrence_count",
        dimensions=["event_type", "month", "weekday"],
        ordering=ordering,
        limit=20,
        items=[
            GroupedItem(
                value=value,
                coordinates=[
                    GroupCoordinate(dimension="event_type", key=str(i), name=name),
                    GroupCoordinate(dimension="month", key=month, name=month),
                    GroupCoordinate(dimension="weekday", key=weekday, name=weekday),
                ],
            )
            for i, (name, value) in enumerate(zip(("Konzert", "Lesung"), values, strict=True))
        ],
    )


@pytest.mark.parametrize(
    "metric,noun",
    [
        ("event_count", "Veranstaltungen"),
        ("occurrence_count", "Termine"),
        ("venue_count", "Orte"),
        ("organization_count", "Organisationen"),
    ],
)
def test_count_labels(metric, noun):
    assert (
        answer(CountResult(metric=metric, value=7)) == f"Für diese Auswahl wurden 7 {noun} gezählt."
    )


def test_singular_and_german_number_format():
    assert (
        answer(CountResult(metric="occurrence_count", value=1))
        == "Für diese Auswahl wurde 1 Termin gezählt."
    )
    assert "1.234 Veranstaltungen" in answer(CountResult(metric="event_count", value=1234))


def test_records_known_total():
    assert (
        answer(records(20, 128))
        == "Es wurden 128 passende Veranstaltungen gefunden; 20 werden angezeigt."
    )
    assert (
        answer(records(0, 128))
        == "Es wurden 128 passende Veranstaltungen gefunden; 0 werden angezeigt."
    )


@pytest.mark.parametrize(
    "entity,noun",
    [("event", "Veranstaltungen"), ("venue", "Orte"), ("organization", "Organisationen")],
)
def test_records_unknown_total(entity, noun):
    assert answer(records(), entity=entity) == f"Es werden 2 passende {noun} angezeigt."


def test_semantic_records_never_use_total():
    value = answer(records(12, 128), semantic=True)
    assert (
        value == "Die semantische Suche zeigt 12 passende Veranstaltungen; "
        "dies ist keine vollständige Zählung."
    )
    assert "128" not in value


@pytest.mark.parametrize(
    "semantic,expected",
    [
        (False, "Für diese Frage wurden keine passenden Ergebnisse gefunden."),
        (True, "Für diese Frage wurden keine ausreichend passenden semantischen Treffer gefunden."),
    ],
)
def test_empty_records(semantic, expected):
    assert answer(records(0), semantic=semantic) == expected


@pytest.mark.parametrize(
    "ordering,label,adjective", [("desc", "Konzert", "höchsten"), ("asc", "Lesung", "niedrigsten")]
)
def test_aggregate_ordering(ordering, label, adjective):
    value = answer(aggregate(), ordering=ordering)
    assert f"„{label}“" in value and f"den {adjective} angezeigten Wert" in value
    assert ("niedrigsten" if ordering == "desc" else "höchsten") not in value
    assert "mit 7 Termine " not in value
    if ordering == "desc":
        assert "mit 7 Terminen" in value


def test_aggregate_neutral():
    assert answer(aggregate(), ordering=None) == "Die Auswertung enthält 2 angezeigte Gruppen."


@pytest.mark.parametrize(
    "ordering,label,adjective", [("desc", "Konzert", "höchsten"), ("asc", "Lesung", "niedrigsten")]
)
def test_grouped_uses_result_ordering_and_complete_localized_cell(ordering, label, adjective):
    value = answer(grouped(ordering), ordering="asc" if ordering == "desc" else "desc")
    assert f"„{label} / September / Sonntag“" in value
    assert f"den {adjective} angezeigten Wert" in value
    assert ("niedrigsten" if ordering == "desc" else "höchsten") not in value
    assert "2026" not in value


def test_grouped_neutral_and_unknown_labels():
    assert answer(grouped(None)) == "Die Auswertung enthält 2 angezeigte Kombinationen."
    assert "Konzert / invalid / unknown" in answer(grouped(month="invalid", weekday="unknown"))


@pytest.mark.parametrize("ordering", ["asc", "desc"])
@pytest.mark.parametrize("kind", ["aggregate", "grouped"])
def test_ties(ordering, kind):
    result = aggregate((7, 7)) if kind == "aggregate" else grouped(ordering, (7, 7))
    value = answer(result, ordering=ordering)
    assert "2 der angezeigten" in value and "teilen sich mit 7 Terminen" in value
    assert "„Konzert" not in value


@pytest.mark.parametrize("ordering", [None, "asc", "desc"])
def test_comparison_remains_factual(ordering):
    result = ComparisonResult(
        metric="event_count",
        items=[
            ComparisonItem(
                target=ResolutionCandidate(entity_type="venue", id=str(i), label=name), value=value
            )
            for i, (name, value) in enumerate([("A", 3), ("B", 7)])
        ],
    )
    assert (
        answer(result, ordering=ordering)
        == "Die Vergleichswerte für 2 Ziele reichen von 3 bis 7 Veranstaltungen."
    )


def test_taxonomy_spatial_and_clarification():
    assert (
        answer(TaxonomyResult(taxonomy="genre", total=18, items=[]))
        == "In den passenden Veranstaltungen werden 18 unterschiedliche Genres verwendet."
    )
    assert (
        answer(SpatialResult(spatial_metric="longitude", ordering="asc", items=records(7).items))
        == "Die räumliche Auswertung zeigt 7 Datensätze mit bekannter Position."
    )
    assert answer(ExecutionClarification(reason="planner", planner_state="needs_context")) is None


def test_long_source_label_is_bounded_without_cutting_off_facts():
    value = answer(aggregate(names=("x" * 5000, "B")))
    assert len(value) <= ANSWER_TEXT_MAX_LENGTH
    assert value == "Der höchste angezeigte Wert beträgt 7 Termine."
    with pytest.raises(ValidationError) as error:
        ResearchExecutionResponse.model_validate({"answer_text": "x" * 1001})
    assert any(
        e["loc"] == ("answer_text",) and e["type"] == "string_too_long"
        for e in error.value.errors()
    )


def test_no_unproven_claims_or_side_effects_and_no_mutation(caplog):
    result = grouped()
    before = result.model_dump_json()
    first = build_research_answer(PLAN, result, PROVENANCE)
    assert first == build_research_answer(PLAN, result, PROVENANCE)
    assert result.model_dump_json() == before
    assert not caplog.records
    for word in ["beliebtest", "beste", "repräsentativ", "weil", "geeignet"]:
        assert word not in first
