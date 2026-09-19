"""DDL-audited integrity checks; all rules are internal only.

Each checker yields field-specific, minimal evidence. The existing engine owns
identity, relevance, persistence and successful coverage semantics.
"""

import hashlib
import json
import re
from collections.abc import Iterator
from datetime import datetime
from typing import TYPE_CHECKING, Any

from email_validator import EmailNotValidError, validate_email

from app.repositories.quality_sources import Sources
from app.schemas.action import Action
from app.schemas.finding import Severity

if TYPE_CHECKING:
    from app.services.quality.core import QualityContext, RuleResult

# rule -> (source/entity kind, field, severity, German message)
RULES = {
    "event_date_end_before_start": (
        "event_date",
        "end_date",
        "error",
        "Das Enddatum liegt vor dem Startdatum.",
    ),
    "event_date_same_day_end_before_start": (
        "event_date",
        "end_time",
        "error",
        "Die Endzeit liegt am selben Tag vor der Startzeit.",
    ),
    "event_date_overnight_without_end_date": (
        "event_date",
        "end_date",
        "info",
        "Die Endzeit liegt vor der Startzeit. Falls der Termin über Mitternacht geht, "
        "sollte ein explizites Enddatum angegeben werden.",
    ),
    "event_price_without_currency": (
        "event",
        "currency",
        "warning",
        "Ein Preis ist angegeben, aber die Währung fehlt.",
    ),
    "event_price_range_invalid": ("event", "price", "error", "Der Preisbereich ist ungültig."),
    "event_free_with_price": (
        "event",
        "price_type",
        "warning",
        "Die kostenlose Veranstaltung enthält eine Preisangabe.",
    ),
    "event_link_empty": (
        "event_link",
        "url",
        "warning",
        "Der Veranstaltungslink enthält keine URL.",
    ),
    "event_link_missing_type": (
        "event_link",
        "type",
        "info",
        "Dem Veranstaltungslink fehlt ein Typ.",
    ),
    "event_link_unknown_type": (
        "event_link",
        "type",
        "warning",
        "Der Veranstaltungslink verwendet einen unbekannten Typ.",
    ),
    "email_syntax": ("contact", "", "warning", "Die E-Mail-Adresse ist syntaktisch ungültig."),
    "postal_code_syntax": (
        "address",
        "postal_code",
        "warning",
        "Die Postleitzahl hat ein ungültiges Format.",
    ),
    "text_surrounding_whitespace": (
        "structured_text",
        "",
        "info",
        "Das strukturierte Feld enthält führende oder abschließende Leerzeichen.",
    ),
    "space_capacity_inconsistent": (
        "space",
        "seating_capacity",
        "warning",
        "Die Sitzplatzkapazität ist größer als die Gesamtkapazität.",
    ),
    "space_capacity_invalid": ("space", "", "error", "Kapazität oder Fläche ist negativ."),
    "released_event_without_description": (
        "event",
        "description",
        "warning",
        "Die veröffentlichte Veranstaltung hat keine Beschreibung.",
    ),
    "released_event_without_categories": (
        "event",
        "categories",
        "warning",
        "Die veröffentlichte Veranstaltung hat keine Kategorie.",
    ),
    "released_event_without_type": (
        "event",
        "event_type_link",
        "warning",
        "Die veröffentlichte Veranstaltung hat keinen Veranstaltungstyp.",
    ),
    "membership_joined_accept_token_present": (
        "team_membership",
        "accept_token",
        "error",
        "Eine bereits angenommene Team-Einladung besitzt noch einen aktiven Einladungstoken.",
    ),
    "event_unknown_category": (
        "event",
        "categories",
        "warning",
        "Die Veranstaltung verwendet eine unbekannte Kategorie.",
    ),
    "event_type_link_unknown_type": (
        "event",
        "event_type_link",
        "warning",
        "Die Veranstaltung verwendet einen unbekannten Veranstaltungstyp.",
    ),
    "event_type_link_unknown_genre": (
        "event",
        "event_type_link",
        "warning",
        "Die Veranstaltung verwendet ein unbekanntes Genre.",
    ),
    "event_unknown_language": (
        "event",
        "languages",
        "warning",
        "Die Veranstaltung verwendet einen unbekannten Sprachcode.",
    ),
}
REASONS = {
    "negative_min_price": "Der Mindestpreis ist negativ.",
    "negative_max_price": "Der Höchstpreis ist negativ.",
    "min_greater_than_max": "Der Mindestpreis ist größer als der Höchstpreis.",
    "negative_total_capacity": "Die Gesamtkapazität ist negativ.",
    "negative_seating_capacity": "Die Sitzplatzkapazität ist negativ.",
    "negative_area_sqm": "Die Fläche ist negativ.",
}
V2_RULES = tuple(RULES)
CONTACT_FIELDS = {
    "organization": ("contact_email",),
    "venue": ("contact_email",),
    "event": ("registration_email",),
}
# postal_code has its own pre-existing whitespace rule; never duplicate it here.
ADDRESS_FIELDS = ("street", "house_number", "city", "country", "state")
TEXT_FIELDS = {
    "organization": ADDRESS_FIELDS,
    "venue": ADDRESS_FIELDS,
    "event": ("registration_email", "registration_phone", "currency"),
    "event_link": ("type", "url"),
}
Issue = tuple[str, dict[str, Any]]


def blank(value: str | None) -> bool:
    return value is None or not value.strip()


def email_problem(value: str | None) -> str | None:
    if blank(value):
        return None
    assert value is not None
    value = value.strip()
    try:
        # Reuse the dependency behind Pydantic EmailStr. test_environment permits
        # reserved .test examples; syntax only, no DNS or deliverability checks.
        validate_email(value, check_deliverability=False, test_environment=True)
    except EmailNotValidError:
        return "missing_at" if "@" not in value else "invalid_syntax"
    return None


def postal_problem(value: str | None, country: str | None) -> str | None:
    if blank(value):
        return None
    assert value is not None
    value = value.strip()  # the existing whitespace rule owns edge whitespace
    code = (country or "").strip().upper()
    digits = {"DE": 5, "DEU": 5, "DK": 4, "DNK": 4}.get(code)
    if digits is not None:
        return None if re.fullmatch(rf"[0-9]{{{digits}}}", value) else "country_format"
    # International codes may contain letters, numbers, spaces and hyphens.
    if any(not (c.isalnum() or c in " -") for c in value):
        return "invalid_characters"
    return None


def date_issues(rule: str, row: dict[str, Any]) -> Iterator[Issue]:
    start, end = row["start_date"], row.get("end_date")
    start_time, end_time = row.get("start_time"), row.get("end_time")
    reversed_time = start_time is not None and end_time is not None and end_time < start_time
    matches = {
        "event_date_end_before_start": end is not None and end < start,
        "event_date_same_day_end_before_start": end == start and reversed_time,
        "event_date_overnight_without_end_date": end is None and reversed_time,
    }
    if matches[rule]:
        yield (
            RULES[rule][1],
            {"start_date": start, "end_date": end, "start_time": start_time, "end_time": end_time},
        )


def event_issues(rule: str, row: dict[str, Any], context: "QualityContext") -> Iterator[Issue]:
    low, high = row.get("min_price"), row.get("max_price")
    priced = low is not None or high is not None
    field = RULES[rule][1]
    if rule == "event_price_without_currency" and priced and blank(row.get("currency")):
        yield field, {"min_price": low, "max_price": high, "currency": row.get("currency")}
    elif rule == "event_free_with_price" and priced and row.get("price_type") == "free":
        yield field, {"min_price": low, "max_price": high, "price_type": "free"}
    elif rule == "event_price_range_invalid":
        if low is not None and low < 0:
            yield "min_price", {"reason": "negative_min_price", "value": low}
        if high is not None and high < 0:
            yield "max_price", {"reason": "negative_max_price", "value": high}
        if low is not None and high is not None and low > high:
            yield "price", {"reason": "min_greater_than_max", "min_price": low, "max_price": high}
    elif (
        rule.startswith("released_event_without_") and context.relevance("event", row)["published"]
    ):
        if rule == "released_event_without_description" and blank(row.get("description")):
            yield field, {field: row.get(field), "release_status": row["release_status"]}
        elif rule == "released_event_without_categories" and not row.get("categories"):
            yield field, {field: row.get(field), "release_status": row["release_status"]}
        elif rule == "released_event_without_type" and str(row["uuid"]) not in context.event_types:
            yield field, {"has_type_link": False, "release_status": row["release_status"]}
    elif rule in {"event_unknown_category", "event_unknown_language"}:
        vocabulary = "event_category" if field == "categories" else "language"
        unknown = set(row.get(field) or ()) - context.vocabularies[vocabulary]
        if unknown:
            yield field, {"unknown": sorted(unknown, key=str)}
    elif rule in {"event_type_link_unknown_type", "event_type_link_unknown_genre"}:
        position, vocabulary = (0, "event_type") if rule.endswith("_type") else (1, "genre_type")
        unknown = {
            pair[position] for pair in context.event_types.get(str(row["uuid"]), set())
        } - context.vocabularies[vocabulary]
        if position == 1:
            unknown.discard(0)  # explicit upstream default: no genre selected
        if unknown:
            yield field, {"unknown": sorted(unknown)}


def issues(rule: str, kind: str, row: dict[str, Any], context: "QualityContext") -> Iterator[Issue]:
    field = RULES[rule][1]
    if rule == "email_syntax":
        for name in CONTACT_FIELDS[kind]:
            if reason := email_problem(row.get(name)):
                yield name, {"reason": reason, "value": row.get(name)}
    elif rule == "postal_code_syntax":
        if reason := postal_problem(row.get(field), row.get("country")):
            yield field, {"reason": reason, "value": row.get(field), "country": row.get("country")}
    elif rule == "text_surrounding_whitespace":
        for name in TEXT_FIELDS[kind]:
            value = row.get(name)
            if value is not None and value != value.strip():
                yield name, {"reason": "leading_or_trailing_whitespace", "value": value}
    elif kind == "event_date":
        yield from date_issues(rule, row)
    elif kind == "event":
        yield from event_issues(rule, row, context)
    elif kind == "event_link":
        value = row.get(field)
        if (rule in {"event_link_empty", "event_link_missing_type"} and blank(value)) or (
            rule == "event_link_unknown_type"
            and not blank(value)
            and value is not None
            and value.strip() not in context.vocabularies["link_type"]
        ):
            yield field, {field: value}
    elif kind == "space":
        total, seating = row.get("total_capacity"), row.get("seating_capacity")
        if (
            rule == "space_capacity_inconsistent"
            and total is not None
            and seating is not None
            and seating > total
        ):
            yield field, {"total_capacity": total, "seating_capacity": seating}
        elif rule == "space_capacity_invalid":
            for name in ("total_capacity", "seating_capacity", "area_sqm"):
                value = row.get(name)
                if value is not None and value < 0:
                    yield name, {"reason": f"negative_{name}", "value": value}
    elif kind == "team_membership" and row["has_joined"] and row["accept_token_present"]:
        yield field, {"token_present": True}


def evaluate_v2(
    rule: str, sources: Sources, now: datetime, context: "QualityContext"
) -> "RuleResult":
    from app.services.quality.core import RuleResult, entity_key, make_finding

    group, _, severity, message = RULES[rule]
    kinds = {
        "contact": tuple(CONTACT_FIELDS),
        "address": ("organization", "venue"),
        "structured_text": tuple(TEXT_FIELDS),
    }.get(group, (group,))
    result = RuleResult(rule)
    for kind in kinds:
        for row in sources.rows[kind]:
            key = entity_key(kind, row)
            result.covered.add((kind, key))
            owner = row
            if kind in {"event_link", "event_date"}:
                owner = context.indexes["event"].get(str(row.get("event_uuid")), {})
            elif kind == "space":
                owner = context.indexes["venue"].get(str(row.get("venue_uuid")), {})
            org = (
                row
                if kind == "organization"
                else context.indexes["organization"].get(str(owner.get("org_uuid")))
            )
            for field, evidence in issues(rule, kind, row, context):
                # Contact values and descriptions are only hashed; safe reason codes
                # and unknown vocabulary IDs explain the issue. Tokens are never loaded.
                metadata = {
                    k: v for k, v in evidence.items() if k in {"reason", "token_present", "unknown"}
                }
                metadata["source_fingerprint"] = hashlib.sha256(
                    json.dumps(evidence, sort_keys=True, default=str).encode()
                ).hexdigest()
                metadata["category"] = (
                    "security"
                    if kind == "team_membership"
                    else "content"
                    if rule.startswith("released_event_without_")
                    else "integrity"
                )
                if rule == "email_syntax":
                    metadata["field"] = field
                finding = make_finding(
                    rule,
                    kind,
                    key,
                    field,
                    REASONS.get(evidence.get("reason", ""), message),
                    now,
                    severity=Severity(severity),
                    name=row.get("name") or owner.get("name"),
                    organization=org,
                    metadata=metadata,
                    **context.relevance(kind, row),
                )
                if kind == "team_membership" and org:
                    finding.action = Action(
                        route="activity", entity_type="organization", entity_key=str(org["uuid"])
                    )
                result.findings.append(finding)
    return result
