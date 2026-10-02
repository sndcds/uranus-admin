"""Conservative multilingual vetoes, never a replacement planner or SQL generator.

A recognized analytical question must not silently degrade to record retrieval.
Unrecognized wording still relies on the closed model and the planning prompt.
"""

import re


def analytical_mismatch(
    query: str,
    intent: str,
    group_by: str,
    planned_taxonomy: str | None = None,
    area_relation: str = "inside",
    time_of_day: str = "none",
) -> bool:
    q = query.casefold()
    if re.search(r"außerhalb|ausserhalb|outside|udenfor", q) and area_relation != "outside":
        return True
    if re.search(r"vormittag|morning|formiddag", q) and time_of_day != "morning":
        return True
    if intent in {"count", "aggregate", "compare"} and re.search(
        r"rollstuhl|barrierefrei|wheelchair|kørestol", q
    ):
        return True  # No authoritative structured accessibility count is implemented.

    # Match the requested subject, not dimension names mentioned later as filters.
    # This is a veto only: never rewrite an unsupported dimension to a supported one.
    occurrence_rank = re.search(r"\b(termine|dates|occurrences|datoer)\b", q) and re.search(
        r"meisten|wenigsten|viele|most|fewest|many|flest|færrest|mange", q
    )
    if occurrence_rank:
        for subject, dimension in (
            (
                r"veranstaltungstyp(?:en)?|event[- ]typ(?:en)?|event[- ]types?|begivenhedstyper?",
                "event_type",
            ),
            (r"genres?", "genre"),
            (r"orte?|veranstaltungsorte?|venues?|steder?", "venue"),
            (r"organisation(?:en)?|organizations?|organisations?|organisationer?", "organization"),
            (r"events?|veranstaltung(?:en)?|begivenhed(?:er)?|arrangement(?:er)?", "event"),
        ):
            if re.search(
                rf"^\s*(?:welche[rsn]?|which|what|hvilke[nt]?)(?:\s+\d+)?\s+(?:{subject})\b",
                q,
            ):
                return intent != "aggregate" or group_by != dimension

    taxonomy = next(
        (
            name
            for pattern, name in (
                (r"\bgenres?\b", "genre"),
                (r"\b(kategorien|categories|kategorier)\b", "category"),
                (r"\b(veranstaltungstypen|event types|begivenhedstyper)\b", "event_type"),
            )
            if re.search(pattern, q)
        ),
        None,
    )
    ranked = bool(
        re.search(r"häufig|meisten|am meisten|particularly active|most |hyppigst|flest", q)
    )
    discovery = bool(re.search(r"welche|what|which|hvilke", q))
    if taxonomy and (ranked or discovery) and not re.search(r"\bmit\b|\bwith\b", q):
        if ranked:
            return intent != "aggregate" or group_by != taxonomy
        return intent != "taxonomy" or planned_taxonomy != taxonomy
    if re.search(
        r"westlichst|östlichst|nördlichst|südlichst|weitesten (west|ost|öst|nord|nörd|süd)"
        r"|westernmost|easternmost|northernmost|southernmost",
        q,
    ):
        return intent != "spatial_rank"
    if re.search(r"wie viele|how many|hvor mange", q):
        return intent not in {"count", "compare"}
    if re.search(r"welche instrumente|which instruments|hvilke instrumenter", q):
        return True  # No evidence-backed extraction contract exists in this version.
    if re.search(r"wo .*viele|wo .*meisten|wo ist am meisten|welche .*orte .*(viel|meisten)", q):
        return intent != "aggregate" or group_by != "venue"
    if re.search(r"wer veranstaltet.*(meisten|viele)", q):
        return intent != "aggregate" or group_by != "organization"
    return False
