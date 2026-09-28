"""Allowlisted public prose and tokenizer-bounded, deterministic event chunks."""

import hashlib
import re
import unicodedata
from collections.abc import Callable, Mapping
from html.parser import HTMLParser
from typing import Any, Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from app.repositories.research import source_url

DOCUMENT_VERSION = "event-public-v1"
CHUNK_VERSION = "sections-480-overlap64-v2"
POINT_NAMESPACE = UUID("f6d7a7df-8744-4d7b-a928-0a3df9335a36")
Kind = Literal[
    "content",
    "participation",
    "accessibility",
    "tickets",
    "additional",
    "facilities",
    "location_context",
    "activities",
    "categories",
]


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Kind
    text: str = Field(min_length=1, max_length=200_000)


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_index: int = Field(ge=0)
    chunk_kind: Kind
    text: str = Field(min_length=1, max_length=200_000)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    token_count: int = Field(ge=1, le=512)


class EventDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: UUID
    title: str
    sections: list[Section]
    payload: dict[str, Any]


class PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "iframe", "object"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "iframe", "object"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def clean(value: object) -> str:
    if value is None:
        return ""
    parser = PlainText()
    parser.feed(str(value))
    text = unicodedata.normalize("NFC", "".join(parser.parts))
    # Free prose can contain contact details even when its database column is public.
    text = re.sub(r"[\w.+%-]+@[\w.-]+\.[A-Za-z]{2,}", "", text)
    text = re.sub(r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b", "", text)
    text = re.sub(r"https?://[^\s<>\)\]]+", lambda m: source_url(m[0]) or "", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip()).strip()


def lines(fields: list[tuple[str, object]], cleaner: Callable[[object], str] = clean) -> str:
    return "\n\n".join(f"{label}: {value}" for label, raw in fields if (value := cleaner(raw)))


def names(values: object) -> str:
    if not isinstance(values, list):
        return ""
    return ", ".join(sorted({clean(v) for v in values if clean(v)}))


def document(
    row: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    cleaner: Callable[[object], str] = clean,
) -> EventDocument:
    """Never iterate arbitrary row keys into either semantic text or payload."""
    title = cleaner(row["title"])
    sections: list[tuple[Kind, list[tuple[str, object]]]] = [
        (
            "content",
            [
                ("Titel", title),
                ("Untertitel", row.get("subtitle")),
                ("Zusammenfassung", row.get("summary")),
                ("Beschreibung", row.get("description")),
                ("Kategorien", names(row.get("category_names"))),
                ("Veranstaltungsarten", names(row.get("type_names"))),
                ("Genres", names(row.get("genre_names"))),
                ("Schlagworte", names(row.get("tags"))),
                ("Veranstalter", row.get("organization_name")),
                ("Orte", names(context.get("venue_names"))),
                ("Räume", names(context.get("space_names"))),
                ("Gemeinden / Kommunen", names(context.get("area_names"))),
                ("Sprache", row.get("language")),
                ("Weitere Sprachen", names(row.get("languages"))),
            ],
        ),
        (
            "participation",
            [
                ("Teilnahme", row.get("participation_info")),
                ("Treffpunkt", row.get("meeting_point")),
                ("Mindestalter", row.get("min_age")),
                ("Höchstalter", row.get("max_age")),
                ("Online-Teilnahme", source_url(row.get("online_link"))),
            ],
        ),
        ("accessibility", [("Barrierefreiheit", names(context.get("accessibility")))]),
        (
            "tickets",
            [
                (
                    "Preisart",
                    {
                        "free": "kostenlos",
                        "regular_price": "regulärer Eintritt",
                        "donation": "Spende",
                        "tiered_prices": "gestaffelte Preise",
                    }.get(row.get("price_type", "")),
                ),
                ("Mindestpreis", row.get("min_price")),
                ("Höchstpreis", row.get("max_price")),
                ("Währung", row.get("currency")),
                (
                    "Ticket- und Anmeldehinweise",
                    names(
                        [
                            {
                                "advance_ticket": "Vorverkauf",
                                "ticket_required": "Ticket erforderlich",
                                "on_site_ticket_sales": "Tickets vor Ort",
                                "registration_required": "Anmeldung erforderlich",
                                "reduced_price_available": "ermäßigter Eintritt verfügbar",
                                "presale_fee_applies": "Vorverkaufsgebühr fällt an",
                            }.get(flag)
                            for flag in (row.get("ticket_flags") or [])
                        ]
                    ),
                ),
                ("Tickets", source_url(row.get("ticket_link"))),
                ("Anmeldung", source_url(row.get("registration_link"))),
                ("Anmeldeschluss", row.get("registration_deadline")),
            ],
        ),
        ("additional", [("Öffentliche Quelle", source_url(row.get("source_link")))]),
    ]
    public_sections = [
        Section(kind=kind, text=text)
        for kind, fields in sections
        if (text := lines(fields, cleaner))
    ]
    if sum(len(s.text) for s in public_sections) > 200_000:
        raise ValueError("event_document_limit")
    payload = {
        "index_owner": "uranus-admin-event-pilot-v1",
        "entity_type": "event",
        "entity_id": str(row["entity_id"]),
        "organization_id": str(row["organization_id"]),
        "category_ids": sorted(set(row.get("category_ids") or [])),
        "status": row["status"],
        "language": row.get("language"),
        "source_updated_at": row["source_updated_at"].isoformat()
        if row.get("source_updated_at")
        else None,
        "document_schema_version": DOCUMENT_VERSION,
        **{key: context.get(key, []) for key in ("venue_ids", "space_ids", "area_ids")},
        **{key: context.get(key) for key in ("first_date", "next_date", "last_date")},
        "area_assignment_available": bool(context.get("area_assignment_available")),
    }
    return EventDocument(
        entity_id=row["entity_id"], title=title, sections=public_sections, payload=payload
    )


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def point_id(entity_id: UUID, chunk: Chunk) -> str:
    return str(uuid5(POINT_NAMESPACE, f"{entity_id}:{chunk.chunk_kind}:{chunk.content_hash}"))


def chunk_sections(
    sections: list[Section],
    count: Callable[[str], int],
    *,
    prefix: str = "",
    maximum: int = 480,
    overlap: int = 64,
) -> list[Chunk]:
    """Native-tokenizer limit includes model prefix and special tokens; never truncate."""
    if not 100 <= maximum <= 480 or not 0 <= overlap < maximum // 2:
        raise ValueError("invalid_chunk_limits")
    combined = "\n\n".join(s.text for s in sections)
    if not combined:
        return []
    chunks: list[tuple[Kind, str]] = []
    if count(prefix + combined) <= maximum:
        chunks.append(("content", prefix + combined))
    else:
        for section in sections:
            remaining = section.text
            while remaining:
                if count(prefix + remaining) <= maximum:
                    chunks.append((section.kind, prefix + remaining))
                    break
                low, high = 1, len(remaining)
                while low < high:
                    middle = (low + high + 1) // 2
                    if count(prefix + remaining[:middle]) <= maximum:
                        low = middle
                    else:
                        high = middle - 1
                cut = low
                # Prefer paragraph/sentence ends, while retaining a useful chunk size.
                boundaries = [m.end() for m in re.finditer(r"\n\n|[.!?]\s+", remaining[:cut])]
                useful = [b for b in boundaries if b >= cut * 0.65]
                if useful:
                    cut = useful[-1]
                raw_part = remaining[:cut]
                part = raw_part.strip()
                if not part or count(prefix + part) > maximum:
                    raise ValueError("tokenizer_cannot_split")
                chunks.append((section.kind, prefix + part))
                low, high = 0, len(raw_part)
                while low < high:
                    middle = (low + high + 1) // 2
                    if count(raw_part[-middle:]) <= overlap:
                        low = middle
                    else:
                        high = middle - 1
                tail = raw_part[-low:] if low else ""
                if len(tail) >= cut:
                    tail = ""
                remaining = tail + remaining[cut:]
                if len(chunks) > 1000:
                    raise ValueError("event_chunk_limit")
    unique = list(dict.fromkeys(chunks))
    return [
        Chunk(
            chunk_index=i,
            chunk_kind=kind,
            text=text,
            content_hash=content_hash(text),
            token_count=count(text),
        )
        for i, (kind, text) in enumerate(unique)
    ]
