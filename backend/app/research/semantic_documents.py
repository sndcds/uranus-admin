"""Explicit public field builders, reusing the event section and normalization pipeline."""

import re
from collections.abc import Mapping
from typing import Any

from app.repositories.activity_previews import location
from app.repositories.research import source_url
from app.research.semantic_contracts import (
    EffectiveLocation,
    EventPayload,
    OrganizationPayload,
    SemanticDocument,
    VenuePayload,
)
from app.research.vector_documents import Kind, Section, clean, document, lines, names


def public_clean(value: object) -> str:
    # Scrub URLs before contacts: deleting an email/UUID must not turn an unsafe URL
    # into a different, apparently valid link. Only explicit HTTP(S) public links survive.
    raw = str(value) if value is not None else ""
    raw = re.sub(
        r"(?:https?://|mailto:|tel:)[^\s<>\)\]]+",
        lambda m: (
            m[0]
            if source_url(m[0])
            and not re.search(r"@|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", m[0])
            else ""
        ),
        raw,
        flags=re.I,
    )
    value_text = clean(raw)
    # Labeled local numbers and recognisable international/German dial prefixes.
    # Do not strip dates, prices, ages, street numbers or postal codes.
    value_text = re.sub(
        r"(?i)\b(?:tel(?:efon(?:nummer)?)?|tlf|phone|mobil(?:e)?|fax|kontakt|contact)\s*[:.]?\s*"
        r"\+?\d[\d ()/.-]{4,80}\d(?!\d)",
        lambda m: "" if sum(c.isdigit() for c in m[0]) >= 7 else m[0],
        value_text,
    )
    value_text = re.sub(
        r"(?<!\w)(?:\+\d{1,3}|00\d{1,3}|0\d{2,5}[ /()-])"
        r"[\d ()/.-]{5,80}\d(?!\w)",
        "",
        value_text,
    )
    value_text = re.sub(r"(?<!\w)0\d{7,14}(?!\w)", "", value_text)
    return "\n".join(" ".join(line.split()) for line in value_text.splitlines() if line.strip())


def is_public_text(value: str) -> bool:
    # Chunking inserts paragraph separators. Whitespace-only normalization does
    # not change evidence, while any removed contact/HTML/unsafe URL fails closed.
    normalized = "\n".join(" ".join(line.split()) for line in value.splitlines() if line.strip())
    return public_clean(value) == normalized


def safe_sections(sections: list[Section]) -> list[Section]:
    return [Section(kind=s.kind, text=t) for s in sections if (t := public_clean(s.text))]


def build_sections(fields: list[tuple[Kind, list[tuple[str, object]]]]) -> list[Section]:
    return [
        Section(kind=kind, text=value)
        for kind, items in fields
        if (value := lines([(label, public_clean(raw)) for label, raw in items]))
    ]


def coordinates(row: Mapping[str, Any]) -> dict[str, float | None]:
    point = location(row.get("latitude"), row.get("longitude"))
    return {
        "latitude": point["latitude"] if point else None,
        "longitude": point["longitude"] if point else None,
    }


def area_values(areas: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "area_ids": sorted({a["id"] for a in areas}),
        "area_names": sorted({public_clean(a["name"]) for a in areas if public_clean(a["name"])}),
    }


def event_document(row: Mapping[str, Any], context: Mapping[str, Any]) -> SemanticDocument:
    legacy = document(row, context, cleaner=public_clean)
    title = public_clean(row["title"])
    locations = [
        EffectiveLocation.model_validate(value) for value in context.get("effective_locations", [])
    ]
    single = locations[0].model_dump() if len(locations) == 1 else {}
    # Legacy payload is itself explicitly allowlisted; validate into a closed v3 model.
    payload = EventPayload.model_validate(
        {
            **legacy.payload,
            "index_owner": "kulturbytes-semantic-search-v1",
            "document_schema_version": "event-public-v3",
            "genre_keys": sorted(set(row.get("genre_keys") or [])),
            "genre_names": sorted(
                {name for raw in row.get("genre_names") or [] if (name := public_clean(raw))}
            ),
            "display_name": title,
            "title": title,
            "language": public_clean(row.get("language")) or None,
            "area_names": [public_clean(n) for n in context.get("area_names", [])],
            "effective_locations": locations,
            **single,
        }
    )
    return SemanticDocument(
        entity_type="event",
        entity_id=legacy.entity_id,
        display_name=title,
        sections=safe_sections(legacy.sections),
        payload=payload,
    )


def venue_document(
    row: Mapping[str, Any], areas: list[dict[str, str]], available: bool
) -> SemanticDocument:
    name = public_clean(row["name"])
    payload = VenuePayload.model_validate(
        {
            "entity_id": row["entity_id"],
            "display_name": name,
            "name": name,
            "scope": row["scope"],
            "organization_id": row["organization_id"],
            "source_updated_at": row["source_updated_at"].isoformat()
            if row.get("source_updated_at")
            else None,
            "area_assignment_available": available,
            **coordinates(row),
            **area_values(areas),
        }
    )
    sections = build_sections(
        [
            (
                "content",
                [
                    ("Name", name),
                    ("Zusammenfassung", row.get("summary")),
                    ("Beschreibung", row.get("description")),
                    ("Ortstyp", row.get("type")),
                    ("Organisation", row.get("organization_name")),
                ],
            ),
            ("accessibility", [("Barrierefreiheit", row.get("accessibility_summary"))]),
            ("facilities", [("Öffnungszeiten", row.get("opening_hours"))]),
            (
                "location_context",
                [
                    ("Straße", row.get("street")),
                    ("Hausnummer", row.get("house_number")),
                    ("Postleitzahl", row.get("postal_code")),
                    ("Ort", row.get("city")),
                    ("Land", row.get("country")),
                    ("Gemeinden / Kommunen", names(payload.area_names)),
                ],
            ),
            (
                "additional",
                [
                    ("Webseite", source_url(row.get("web_link"))),
                    ("Tickets", source_url(row.get("ticket_link"))),
                    ("Tickethinweise", row.get("ticket_info")),
                ],
            ),
        ]
    )
    return SemanticDocument(
        entity_type="venue",
        entity_id=payload.entity_id,
        display_name=name,
        sections=sections,
        payload=payload,
    )


def organization_document(
    row: Mapping[str, Any],
    home: list[dict[str, str]],
    activity: list[dict[str, str]],
    available: bool,
) -> SemanticDocument:
    name = public_clean(row["name"])
    home_values, activity_values = area_values(home), area_values(activity)
    payload = OrganizationPayload.model_validate(
        {
            "entity_id": row["entity_id"],
            "display_name": name,
            "name": name,
            "source_updated_at": row["source_updated_at"].isoformat()
            if row.get("source_updated_at")
            else None,
            "area_assignment_available": available,
            **coordinates(row),
            "home_area_ids": home_values["area_ids"],
            "home_area_names": home_values["area_names"],
            "activity_area_ids": activity_values["area_ids"],
            "activity_area_names": activity_values["area_names"],
        }
    )
    sections = build_sections(
        [
            ("content", [("Name", name), ("Beschreibung", row.get("description"))]),
            ("activities", [("Öffentliche Aktivitäten in", names(payload.activity_area_names))]),
            ("additional", [("Webseite", source_url(row.get("web_link")))]),
        ]
    )
    return SemanticDocument(
        entity_type="organization",
        entity_id=payload.entity_id,
        display_name=name,
        sections=sections,
        payload=payload,
    )
