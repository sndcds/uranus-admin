"""Bounded, identity-free factual projection for deterministic conversational rendering."""

from typing import Annotated, Literal

from pydantic import Field

from app.research.plan import InternalResearchPlan
from app.research.wire.research_v13_schema import AnswerLanguage, ConversationV13
from app.schemas.research_execution import ExecutionMetric, ExecutionProvenance, ExecutionResult
from app.schemas.research_values import ClosedModel


class AnswerCell(ClosedModel):
    # Only display labels, never keys, records, coordinates, SQL or vector scores.
    labels: list[Annotated[str, Field(max_length=160)]] = Field(max_length=3)
    dimensions: list[Annotated[str, Field(max_length=32)]] = Field(max_length=3)
    value: int = Field(ge=0)


class AnswerFacts(ClosedModel):
    kind: Literal[
        "count",
        "records",
        "aggregate",
        "grouped",
        "comparison",
        "taxonomy",
        "spatial",
        "needs_clarification",
    ]
    metric: ExecutionMetric | None = None
    value: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)
    shown: int = Field(ge=0, le=100)
    semantic: bool = False
    ordering: Literal["asc", "desc"] | None = None
    cells: list[AnswerCell] = Field(default_factory=list, max_length=20)
    candidates: list[Annotated[str, Field(max_length=160)]] = Field(
        default_factory=list, max_length=5
    )
    clarification: (
        Literal["needs_context", "needs_date", "needs_location", "needs_criteria", "ambiguous"]
        | None
    ) = None


def project_answer_facts(
    plan: InternalResearchPlan, result: ExecutionResult, execution: ExecutionProvenance
) -> AnswerFacts:
    """Explicit allowlist only. This function never serializes a source record."""
    if result.kind == "needs_clarification":
        reason = result.planner_state
        return AnswerFacts(
            kind=result.kind,
            shown=0,
            clarification=reason if reason != "none" else "ambiguous",
            candidates=[c.label for c in result.candidates[:5] if len(c.label) <= 160],
        )
    if result.kind == "count":
        return AnswerFacts(kind=result.kind, metric=result.metric, value=result.value, shown=0)
    cells: list[AnswerCell] = []
    if result.kind == "grouped":
        for cell in result.items[:20]:
            labels = [c.name for c in cell.coordinates]
            cells.append(
                AnswerCell(
                    labels=labels if all(len(n) <= 160 for n in labels) else [],
                    dimensions=[c.dimension for c in cell.coordinates]
                    if all(len(n) <= 160 for n in labels)
                    else [],
                    value=cell.value,
                )
            )
    elif result.kind == "aggregate":
        cells = [
            AnswerCell(
                labels=[item.name] if len(item.name) <= 160 else [],
                dimensions=[result.group_by] if len(item.name) <= 160 else [],
                value=item.value,
            )
            for item in result.items[:20]
        ]
    elif result.kind == "comparison":
        cells = [
            AnswerCell(
                labels=[item.target.label] if len(item.target.label) <= 160 else [],
                dimensions=["target"] if len(item.target.label) <= 160 else [],
                value=item.value,
            )
            for item in result.items[:20]
        ]

    return AnswerFacts(
        kind=result.kind,
        shown=len(result.items),
        semantic=execution.semantic,
        total=result.total if (result.kind == "records" or result.kind == "taxonomy") else None,
        metric=result.metric
        if (result.kind == "grouped" or result.kind == "aggregate" or result.kind == "comparison")
        else None,
        ordering=result.ordering if result.kind == "grouped" else plan.ordering,
        cells=cells,
    )


NOUNS = {
    "de": {
        "event_count": ("Veranstaltung", "Veranstaltungen"),
        "occurrence_count": ("Termin", "Termine"),
        "venue_count": ("Ort", "Orte"),
        "organization_count": ("Organisation", "Organisationen"),
    },
    "en": {
        "event_count": ("event", "events"),
        "occurrence_count": ("occurrence", "occurrences"),
        "venue_count": ("venue", "venues"),
        "organization_count": ("organization", "organizations"),
    },
    "da": {
        "event_count": ("arrangement", "arrangementer"),
        "occurrence_count": ("forekomst", "forekomster"),
        "venue_count": ("sted", "steder"),
        "organization_count": ("organisation", "organisationer"),
    },
}
MONTHS = {
    "de": (
        "Januar Februar März April Mai Juni Juli August September Oktober November Dezember"
    ).split(),
    "en": (
        "January February March April May June July August September October November December"
    ).split(),
    "da": (
        "januar februar marts april maj juni juli august september oktober november december"
    ).split(),
}
WEEKDAYS = {
    "de": "Montag Dienstag Mittwoch Donnerstag Freitag Samstag Sonntag".split(),
    "en": "Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split(),
    "da": "mandag tirsdag onsdag torsdag fredag lørdag søndag".split(),
}


def _choose(language: AnswerLanguage, de: str, da: str, en: str) -> str:
    return {"de": de, "da": da, "en": en}[language]


def _number(value: int, language: AnswerLanguage) -> str:
    return f"{value:,}".replace(",", ".") if language != "en" else f"{value:,}"


def _amount(value: int, metric: ExecutionMetric | None, language: AnswerLanguage) -> str:
    nouns = NOUNS[language].get(
        metric or "",
        _choose(language, "Ergebnis Ergebnisse", "resultat resultater", "result results").split(),
    )
    return f"{_number(value, language)} {nouns[value != 1]}"


def _label(cell: AnswerCell, language: AnswerLanguage) -> str:
    labels = []
    for dimension, name in zip(cell.dimensions, cell.labels, strict=True):
        lookup = (
            MONTHS[language]
            if dimension == "month"
            else WEEKDAYS[language]
            if dimension == "weekday"
            else []
        )
        labels.append(
            lookup[int(name) - 1]
            if lookup and name.isascii() and name.isdigit() and 1 <= int(name) <= len(lookup)
            else name
        )
    return " / ".join(labels)


def render_facts(facts: AnswerFacts, language: AnswerLanguage, *, variant: int = 0) -> str:
    if facts.kind == "needs_clarification":
        if facts.candidates:
            choices = " / ".join(facts.candidates)
            return _choose(
                language,
                f"Welche Zuordnung meinst du: {choices}?",
                f"Hvilken mener du: {choices}?",
                f"Which match do you mean: {choices}?",
            )
        return render_conversation(
            ConversationV13(
                act="clarify",
                reason=facts.clarification
                if facts.clarification != "ambiguous"
                else "needs_definition",
            ),
            language,
        )
    if facts.kind == "count":
        assert facts.value is not None
        amount = _amount(facts.value, facts.metric, language)
        return _choose(
            language,
            f"Ich habe {amount} gefunden."
            if variant % 2 == 0
            else f"Für deine Auswahl {'ist es' if facts.value == 1 else 'sind es'} {amount}.",
            f"Jeg har fundet {amount}.",
            f"I found {amount}.",
        )
    if facts.kind in {"grouped", "aggregate"} and facts.cells and facts.ordering:
        extreme = (min if facts.ordering == "asc" else max)(c.value for c in facts.cells)
        winners = [c for c in facts.cells if c.value == extreme]
        amount = _amount(extreme, facts.metric, language)
        qualifier = _choose(
            language,
            "niedrigsten" if facts.ordering == "asc" else "höchsten",
            "laveste" if facts.ordering == "asc" else "højeste",
            "lowest" if facts.ordering == "asc" else "highest",
        )
        label = _label(winners[0], language)
        if len(winners) == 1 and label:
            return _choose(
                language,
                f"„{label}“ hat den {qualifier} Wert in den angezeigten Daten: {amount}.",
                f"„{label}“ har den {qualifier} værdi i de viste data: {amount}.",
                f"“{label}” has the {qualifier} value in the displayed data: {amount}.",
            )
        return _choose(
            language,
            f"Der {qualifier[:-1]} angezeigte Wert ist {amount}; "
            f"{len(winners)} Gruppen erreichen ihn.",
            f"Den {qualifier} viste værdi er {amount}; {len(winners)} grupper deler den.",
            f"The {qualifier} displayed value is {amount}, shared by {len(winners)} groups.",
        )
    if facts.kind == "comparison" and facts.cells:
        low, high = min(c.value for c in facts.cells), max(c.value for c in facts.cells)
        return _choose(
            language,
            f"Je Vergleichsziel sind es {_number(low, language)} bis "
            f"{_amount(high, facts.metric, language)}.",
            f"Værdierne går fra {_number(low, language)} til "
            f"{_amount(high, facts.metric, language)}.",
            f"The compared values range from {_number(low, language)} to "
            f"{_amount(high, facts.metric, language)}.",
        )
    if facts.semantic:
        return _choose(
            language,
            f"Die semantische Suche zeigt {facts.shown} "
            f"{'passenden Treffer' if facts.shown == 1 else 'passende Treffer'}. "
            f"Das ist keine vollständige Zählung.",
            f"Den semantiske søgning viser {facts.shown} "
            f"{'relevant resultat' if facts.shown == 1 else 'relevante resultater'}. "
            "Det er ikke en fuldstændig optælling.",
            f"Semantic search returned {facts.shown} relevant "
            f"{'match' if facts.shown == 1 else 'matches'}. This "
            f"is not a complete count.",
        )
    if facts.kind == "taxonomy":
        return _choose(
            language,
            f"In deiner Auswahl {'wird' if facts.total == 1 else 'werden'} {facts.total} "
            f"{'Begriff' if facts.total == 1 else 'unterschiedliche Begriffe'} verwendet; "
            f"angezeigt: {facts.shown}.",
            f"Dit udvalg bruger {facts.total} "
            f"{'betegnelse' if facts.total == 1 else 'forskellige betegnelser'}; "
            f"vist: {facts.shown}.",
            f"Your selection uses {facts.total} distinct "
            f"{'term' if facts.total == 1 else 'terms'}; shown: {facts.shown}.",
        )
    if facts.total == 1:
        return _choose(
            language,
            f"Ich habe ein passendes Ergebnis gefunden; angezeigt: {facts.shown}.",
            f"Jeg har fundet ét resultat; vist: {facts.shown}.",
            f"I found one matching result; shown: {facts.shown}.",
        )
    if facts.total is not None:
        return _choose(
            language,
            f"Ich habe {facts.total} passende Ergebnisse gefunden. Hier "
            f"siehst du {facts.shown} davon.",
            f"Jeg har fundet {facts.total} resultater. Her vises {facts.shown} af dem.",
            f"I found {facts.total} matching results. Here are {facts.shown} of them.",
        )
    if facts.shown == 0:
        return _choose(
            language,
            "Dazu habe ich keine passenden Ergebnisse gefunden.",
            "Jeg fandt ingen passende resultater.",
            "I found no matching results.",
        )
    if facts.shown == 1:
        return _choose(
            language,
            "Hier siehst du ein Ergebnis für deine Auswahl.",
            "Her er ét resultat for dit udvalg.",
            "Here is one result for your selection.",
        )
    return _choose(
        language,
        f"Hier siehst du {facts.shown} Ergebnisse für deine Auswahl.",
        f"Her er {facts.shown} resultater for dit udvalg.",
        f"Here are {facts.shown} results for your selection.",
    )


def render_conversation(
    directive: ConversationV13,
    language: AnswerLanguage,
    *,
    facts: AnswerFacts | None = None,
    variant: int = 0,
) -> str:
    act = directive.act
    if act in {"repeat_previous", "simplify_previous", "explain_previous"}:
        if facts is None:
            return render_conversation(
                ConversationV13(act="clarify", reason="needs_context"), language
            )
        text = render_facts(facts, language, variant=variant)
        if act == "explain_previous":
            text += _choose(
                language,
                " Das beschreibt die angezeigten Daten; Ursachen lassen "
                "sich daraus allein nicht ableiten.",
                " Det beskriver de viste data; årsager kan ikke udledes af det alene.",
                " This describes the displayed data; it does not establish causes.",
            )
        return text
    if act == "clarify":
        return {
            "needs_date": _choose(
                language,
                "Welchen Zeitraum meinst du?",
                "Hvilken periode mener du?",
                "Which time period do you mean?",
            ),
            "needs_location": _choose(
                language,
                "Welchen Ort oder welches Gebiet meinst du?",
                "Hvilket sted eller område mener du?",
                "Which place or area do you mean?",
            ),
            "needs_context": _choose(
                language,
                "Worauf beziehst du dich? Nenne bitte das Thema oder die "
                "gemeinten Ergebnisse genauer.",
                "Hvad henviser du til? Angiv emnet eller resultaterne lidt mere præcist.",
                "What are you referring to? Please specify the topic or results.",
            ),
            "needs_criteria": _choose(
                language,
                "Nach welchen Kriterien soll ich die Auswahl vergleichen?",
                "Hvilke kriterier skal jeg sammenligne efter?",
                "Which criteria should I compare?",
            ),
        }.get(
            directive.reason or "",
            _choose(
                language,
                "Was genau möchtest du herausfinden?",
                "Hvad vil du gerne finde ud af?",
                "What would you like to find out?",
            ),
        )
    answers = {
        "acknowledge": _choose(
            language,
            "Gerne." if variant % 2 == 0 else "Sehr gern.",
            "Det var så lidt.",
            "You're welcome.",
        ),
        "pleased": _choose(language, "Freut mich.", "Det glæder mig.", "Glad that helped."),
        "greet": _choose(
            language,
            "Hallo! Was möchtest du über die Kulturbytes-Daten herausfinden?",
            "Hej! Hvad vil du gerne undersøge i Kulturbytes-data?",
            "Hello! What would you like to explore in the Kulturbytes data?",
        ),
        "greet_morning": _choose(
            language,
            "Guten Morgen! Was möchtest du recherchieren?",
            "Godmorgen! Hvad vil du gerne undersøge?",
            "Good morning! What would you like to research?",
        ),
        "social": _choose(
            language,
            "Ich bin bereit, dir bei der Kulturbytes-Recherche zu helfen. Was interessiert dich?",
            "Jeg er klar til at hjælpe med Kulturbytes. Hvad interesserer dig?",
            "I'm ready to help with Kulturbytes research. What interests you?",
        ),
        "help": _choose(
            language,
            "Ich kann Veranstaltungen, Orte und Organisationen finden, nach "
            "Zeiträumen und Regionen eingrenzen, Veranstaltungstypen und "
            "Genres auswerten sowie Häufigkeiten, Vergleiche und saisonale "
            "Verteilungen zeigen. Du kannst auch in eigenen Worten nach "
            "passenden Veranstaltungen suchen und mit Folgefragen die "
            "Auswahl verfeinern.",
            "Jeg kan finde arrangementer, steder og organisationer, "
            "afgrænse efter tid og område og vise typer, genrer, antal, "
            "sammenligninger og sæsonfordelinger. Du kan også søge med dine "
            "egne ord og præcisere med opfølgende spørgsmål.",
            "I can find events, venues and organizations, narrow by time "
            "and area, and show types, genres, counts, comparisons and "
            "seasonal distributions. You can also search in your own words "
            "and refine the selection with follow-up questions.",
        ),
        "unsupported": _choose(
            language,
            "Diese Auswertung kann ich mit den verfügbaren Daten noch nicht "
            "zuverlässig beantworten. Möchtest du deine Frage eingrenzen?",
            "Jeg kan endnu ikke besvare den analyse pålideligt med de "
            "tilgængelige data. Vil du afgrænse spørgsmålet?",
            "I cannot reliably answer that analysis with the available data "
            "yet. Would you like to narrow the question?",
        ),
    }
    return answers[act]
