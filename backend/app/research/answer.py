"""Pure German answer text from the executed selection, never model prose or SQL."""

from typing import Literal, assert_never

from app.research.plan import InternalResearchPlan
from app.schemas.research_execution import (
    ExecutionMetric,
    ExecutionProvenance,
    ExecutionResult,
)

ANSWER_TEXT_MAX_LENGTH = 1000
# Nominative singular/plural and dative singular/plural, respectively.
_METRICS: dict[ExecutionMetric, tuple[str, str, str, str]] = {
    "event_count": ("Veranstaltung", "Veranstaltungen", "Veranstaltung", "Veranstaltungen"),
    "occurrence_count": ("Termin", "Termine", "Termin", "Terminen"),
    "venue_count": ("Ort", "Orte", "Ort", "Orten"),
    "organization_count": ("Organisation", "Organisationen", "Organisation", "Organisationen"),
}
_MONTHS = dict(
    zip(
        (f"{n:02}" for n in range(1, 13)),
        (
            "Januar",
            "Februar",
            "März",
            "April",
            "Mai",
            "Juni",
            "Juli",
            "August",
            "September",
            "Oktober",
            "November",
            "Dezember",
        ),
        strict=True,
    )
)
_WEEKDAYS = dict(
    zip(
        (str(n) for n in range(1, 8)),
        ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"),
        strict=True,
    )
)


def _number(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _metric(value: int, metric: ExecutionMetric, *, dative: bool = False) -> str:
    noun = _METRICS[metric][(2 if dative else 0) + (0 if value == 1 else 1)]
    return f"{_number(value)} {noun}"


def _coordinate(dimension: str, name: str) -> str:
    # Closed recurring calendar labels; no date parsing or implied year.
    labels = _MONTHS if dimension == "month" else _WEEKDAYS if dimension == "weekday" else {}
    return labels.get(name, name)


def _groups(
    cells: list[tuple[str, int]],
    metric: ExecutionMetric,
    ordering: Literal["asc", "desc"] | None,
    *,
    grouped: bool,
) -> str:
    noun = "Kombinationen" if grouped else "Gruppen"
    if not cells:
        return "Für diese Auswertung wurden keine passenden Gruppen gefunden."
    if ordering is None:
        if len(cells) == 1:
            return f"Die Auswertung enthält 1 angezeigte {'Kombination' if grouped else 'Gruppe'}."
        return f"Die Auswertung enthält {_number(len(cells))} angezeigte {noun}."
    extreme = (min if ordering == "asc" else max)(value for _, value in cells)
    labels = [name for name, value in cells if value == extreme]
    adjective = "niedrigsten" if ordering == "asc" else "höchsten"
    amount = _metric(extreme, metric, dative=True)
    if len(labels) > 1:
        return (
            f"{_number(len(labels))} der angezeigten {noun} teilen sich mit {amount} "
            f"den {adjective} angezeigten Wert."
        )
    sentence = (
        f"Unter den angezeigten {noun} hat „{labels[0]}“ mit {amount} "
        f"den {adjective} angezeigten Wert."
    )
    if len(sentence) > ANSWER_TEXT_MAX_LENGTH:
        # Source names are not bounded. Omit the label instead of truncating facts.
        short_adjective = "niedrigste" if ordering == "asc" else "höchste"
        return f"Der {short_adjective} angezeigte Wert beträgt {_metric(extreme, metric)}."
    return sentence


def build_research_answer(
    plan: InternalResearchPlan,
    result: ExecutionResult,
    execution: ExecutionProvenance,
) -> str | None:
    """Return bounded prose for actual results; resolution/SQL are deliberately unused."""
    text = _answer(plan, result, execution)
    if text is not None and len(text) > ANSWER_TEXT_MAX_LENGTH:
        return "Das Ergebnis dieser Auswertung ist in der folgenden Darstellung enthalten."
    return text


def _answer(
    plan: InternalResearchPlan, result: ExecutionResult, execution: ExecutionProvenance
) -> str | None:
    if result.kind == "needs_clarification":
        return None
    if result.kind == "count":
        verb = "wurde" if result.value == 1 else "wurden"
        return f"Für diese Auswahl {verb} {_metric(result.value, result.metric)} gezählt."
    if result.kind == "records":
        size = len(result.items)
        if execution.semantic:
            if not size:
                return (
                    "Für diese Frage wurden keine ausreichend passenden "
                    "semantischen Treffer gefunden."
                )
            return (
                f"Die semantische Suche zeigt {_number(size)} passende "
                f"{'Veranstaltung' if size == 1 else 'Veranstaltungen'}; "
                "dies ist keine vollständige Zählung."
            )
        singular, plural = {
            "event": ("passende Veranstaltung", "passende Veranstaltungen"),
            "venue": ("passender Ort", "passende Orte"),
            "organization": ("passende Organisation", "passende Organisationen"),
        }[plan.entity_type]
        if result.total is not None and result.total > 0:
            noun = singular if result.total == 1 else plural
            verb = "wurde" if result.total == 1 else "wurden"
            shown = "wird" if size == 1 else "werden"
            return (
                f"Es {verb} {_number(result.total)} {noun} gefunden; "
                f"{_number(size)} {shown} angezeigt."
            )
        if not size:
            return "Für diese Frage wurden keine passenden Ergebnisse gefunden."
        return (
            f"Es {'wird' if size == 1 else 'werden'} {_number(size)} "
            f"{singular if size == 1 else plural} angezeigt."
        )
    if result.kind == "aggregate":
        return _groups(
            [(_coordinate(result.group_by, item.name), item.value) for item in result.items],
            result.metric,
            plan.ordering,
            grouped=False,
        )
    if result.kind == "grouped":
        return _groups(
            [
                (" / ".join(_coordinate(c.dimension, c.name) for c in item.coordinates), item.value)
                for item in result.items
            ],
            result.metric,
            result.ordering,
            grouped=True,
        )
    if result.kind == "comparison":
        values = [item.value for item in result.items]
        # Comparison alone does not establish an optimization/quality criterion.
        return (
            f"Die Vergleichswerte für {_number(len(values))} Ziele reichen von "
            f"{_number(min(values))} bis {_metric(max(values), result.metric, dative=True)}."
        )
    if result.kind == "taxonomy":
        noun = {
            "genre": ("Genre", "Genres"),
            "event_type": ("Veranstaltungstyp", "Veranstaltungstypen"),
            "category": ("Kategorie", "Kategorien"),
        }[result.taxonomy][0 if result.total == 1 else 1]
        if result.total == 1:
            return f"In den passenden Veranstaltungen wird 1 {noun} verwendet."
        return (
            f"In den passenden Veranstaltungen werden {_number(result.total)} "
            f"unterschiedliche {noun} verwendet."
        )
    if result.kind == "spatial":
        size = len(result.items)
        return (
            f"Die räumliche Auswertung zeigt {_number(size)} "
            f"{'Datensatz' if size == 1 else 'Datensätze'} mit bekannter Position."
        )
    assert_never(result)
