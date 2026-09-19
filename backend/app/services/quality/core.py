import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from app.config import Settings
from app.repositories.quality_sources import Sources
from app.repositories.temporal import is_upcoming_start
from app.schemas.action import Action
from app.schemas.finding import Finding, Severity
from app.services.quality.priority import priority_details
from app.services.quality.rules.v2 import V2_RULES, evaluate_v2
from app.services.quality.urls import url_problem, valid_online

URL_FIELDS = {
    "organization": ("web_link",),
    "venue": ("web_link", "ticket_link"),
    "space": ("web_link",),
    "event": ("source_link", "online_link", "ticket_link", "registration_link"),
    "event_date": ("ticket_link",),
    "event_link": ("url",),
    "license": ("url",),
}
IMAGE_IDENTIFIERS = {
    "organization": {"main_logo", "dark_theme_logo", "light_theme_logo", "avatar"},
    "venue": {
        "main_logo",
        "dark_theme_logo",
        "light_theme_logo",
        "avatar",
        "main_photo",
        "gallery_photo_1",
        "gallery_photo_2",
        "gallery_photo_3",
    },
    "event": {
        "main",
        "gallery_image_1",
        "gallery_image_2",
        "gallery_image_3",
        "some_16x9",
        "some_1x1",
        "some_4x5",
        "some_9x16",
        "ad_1x1",
        "ad_9x16",
        "ad_16x9",
        "poster",
        "insta_5x4",
    },
    "portal": {"web_logo", "background_image", "footer_logo", "main_image"},
}
LOGO_IDENTIFIERS = {"main_logo", "dark_theme_logo", "light_theme_logo"}
LOGO_MIME_TYPES = ("image/png", "image/webp")
CORE_RULES = (
    *V2_RULES,
    "organization_missing_location",
    "venue_missing_location",
    "url_syntax",
    "postal_code_whitespace",
    "event_without_dates",
    "event_date_without_location",
    "event_without_location",
    "event_date_space_venue_mismatch",
    "image_link_without_image",
    "image_link_unknown_context",
    "image_link_invalid_identifier",
    "image_link_missing_target",
    "image_orphaned_upload",
    "venue_missing_logo",
    "organization_missing_logo",
    "logo_unsupported_format",
)


@dataclass
class RuleResult:
    rule: str
    findings: list[Finding] = field(default_factory=list)
    covered: set[tuple[str, str]] = field(default_factory=set)
    success: bool = True


def entity_key(kind: str, row: dict[str, Any]) -> str:
    if kind == "team_membership":
        return f"membership:{row['org_uuid']}:{row['user_uuid']}"
    if kind == "image_link":
        return "image-link:" + ":".join(
            quote(str(row[key]), safe="") for key in ("context", "context_uuid", "identifier")
        )
    return str(row.get("uuid", row.get("id", row.get("key"))))


def make_finding(
    rule: str,
    kind: str,
    key: str,
    field_name: str,
    message: str,
    now: datetime,
    *,
    severity: Severity = Severity.warning,
    name: str | None = None,
    organization: dict[str, Any] | None = None,
    published: bool = False,
    soon: bool = False,
    upcoming: bool = False,
    metadata: dict[str, Any] | None = None,
) -> Finding:
    action = None
    if kind in {"organization", "venue", "space", "event", "event_date", "user", "image"}:
        action = Action.model_validate(
            {"route": "activity", "entity_type": kind, "entity_key": key}
        )
    return Finding(
        action=action,
        id=":".join(quote(part, safe="") for part in (rule, kind, key, field_name)),
        rule=rule,
        entity_type=kind,
        entity_key=key,
        entity_name=name or key,
        organization_id=organization["uuid"] if organization else None,
        organization_name=organization["name"] if organization else None,
        field=field_name,
        message=message,
        severity=severity,
        last_seen_at=now,
        metadata=metadata or {},
        **priority_details(severity, published=published, soon=soon, upcoming=upcoming),
    )


def effective_location(date: dict[str, Any], event: dict[str, Any]) -> tuple[Any, Any]:
    """Return effective venue/space; a date venue override stops event-space inheritance."""
    if date["venue_uuid"] is not None:
        return date["venue_uuid"], date["space_uuid"]
    return event.get("venue_uuid"), date["space_uuid"] or event.get("space_uuid")


class QualityContext:
    """One immutable source snapshot's indexes and relevance aggregates, built in O(rows)."""

    def __init__(self, sources: Sources, settings: Settings, now: datetime) -> None:
        self.indexes = {
            kind: sources.index(kind)
            for kind in ("organization", "venue", "space", "event", "image")
        }
        self.dates_by_event: dict[str, list[dict[str, Any]]] = {}
        self.event_types: dict[str, set[tuple[int, int]]] = {}
        for link in sources.rows.get("event_type_link", []):
            self.event_types.setdefault(str(link["event_uuid"]), set()).add(
                (link["type_id"], link["genre_id"])
            )
        self.vocabularies = {
            kind: {row[column] for row in sources.rows.get(kind, [])}
            for kind, column in {
                "event_category": "category_id",
                "event_type": "type_id",
                "genre_type": "genre_id",
                "language": "code_iso_639_1",
                "link_type": "key",
            }.items()
        }
        self.flags: dict[tuple[str, str], dict[str, bool]] = {}
        local = now.astimezone(ZoneInfo(settings.event_timezone))
        events = self.indexes["event"]
        for key, event in events.items():
            self.flags[("event", key)] = {
                "published": event["release_status"] in {"released", "rescheduled"},
                "upcoming": False,
                "soon": False,
            }
        for date in sources.rows["event_date"]:
            event_key = str(date["event_uuid"])
            self.dates_by_event.setdefault(event_key, []).append(date)
            parent = events.get(event_key, {})
            upcoming = is_upcoming_start(date, local)
            released = parent.get("release_status") in {"released", "rescheduled"} and date[
                "release_status"
            ] in {"inherited", "released", "rescheduled", None}
            soon = (
                upcoming
                and released
                and date["start_date"] < (local.date() + timedelta(days=settings.upcoming_days))
            )
            self.flags[("event_date", str(date["uuid"]))] = {
                "published": released,
                "upcoming": upcoming,
                "soon": soon,
            }
            effective_venue, effective_space = effective_location(date, parent)
            for kind, key in (
                ("event", event_key),
                ("venue", str(effective_venue)),
                ("space", str(effective_space)),
                ("organization", str(parent.get("org_uuid"))),
            ):
                flags = self.flags.setdefault(
                    (kind, key),
                    {
                        "published": False,
                        "upcoming": False,
                        "soon": False,
                    },
                )
                if kind != "event":
                    flags["published"] |= upcoming and released
                flags["upcoming"] |= upcoming
                flags["soon"] |= soon

    def relevance(self, kind: str, row: dict[str, Any]) -> dict[str, bool]:
        if kind == "event_link":
            kind, key = "event", str(row["event_uuid"])
        else:
            key = str(row.get("uuid"))
        return self.flags.get((kind, key), {"published": False, "upcoming": False, "soon": False})


def evaluate_core(
    rule: str,
    sources: Sources,
    settings: Settings,
    now: datetime,
    scan_context: QualityContext | None = None,
) -> RuleResult:
    result = RuleResult(rule)
    scan_context = scan_context or QualityContext(sources, settings, now)
    if rule in V2_RULES:
        return evaluate_v2(rule, sources, now, scan_context)
    orgs, venues, spaces, events = (
        scan_context.indexes[kind] for kind in ("organization", "venue", "space", "event")
    )
    dates = scan_context.dates_by_event
    relevance = scan_context.relevance

    def organization(kind: str, row: dict[str, Any]) -> dict[str, Any] | None:
        if kind == "image_link":
            target_kind = row["context"]
            if target_kind in {"organization", "venue", "event"}:
                target = scan_context.indexes[target_kind].get(str(row["context_uuid"]))
                return organization(target_kind, target) if target else None
            return None
        if kind == "organization":
            return row
        if kind == "space":
            row = venues.get(str(row.get("venue_uuid")), {})
        elif kind in {"event_date", "event_link"}:
            row = events.get(str(row.get("event_uuid")), {})
        return orgs.get(str(row.get("org_uuid")))

    def emit(
        kind: str,
        row: dict[str, Any],
        field_name: str,
        message: str,
        severity: Severity = Severity.warning,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        result.findings.append(
            make_finding(
                rule,
                kind,
                entity_key(kind, row),
                field_name,
                message,
                now,
                severity=severity,
                name=row.get("name") or events.get(str(row.get("event_uuid")), {}).get("name"),
                organization=organization(kind, row),
                metadata={
                    **(metadata or {}),
                    "source_fingerprint": hashlib.sha256(
                        json.dumps(row, sort_keys=True, default=str).encode()
                    ).hexdigest(),
                },
                **relevance(kind, row),
            )
        )

    if rule in {"organization_missing_location", "venue_missing_location"}:
        kind = "organization" if rule == "organization_missing_location" else "venue"
        for row in sources.rows[kind]:
            result.covered.add((kind, entity_key(kind, row)))
            if row["point_missing"]:
                emit(
                    kind,
                    row,
                    "point",
                    "Organisation hat keine Geoposition."
                    if kind == "organization"
                    else "Veranstaltungsort hat keine Geoposition.",
                    metadata={"geocode_supported": True},
                )
    elif rule == "url_syntax":
        for kind, fields in URL_FIELDS.items():
            for row in sources.rows[kind]:
                result.covered.add((kind, entity_key(kind, row)))
                for name in fields:
                    problem = url_problem(row[name])
                    if problem:
                        emit(
                            kind,
                            row,
                            name,
                            f"URL-Syntax ungültig: {problem}.",
                            metadata={"reason": problem},
                        )
    elif rule == "postal_code_whitespace":
        # Authoritative owners only: projections would multiply the same venue issue.
        for kind in ("organization", "venue"):
            for row in sources.rows[kind]:
                result.covered.add((kind, entity_key(kind, row)))
                postal_code = row["postal_code"]
                # Internal spaces are valid in international postal codes.
                if postal_code is not None and postal_code != postal_code.strip():
                    emit(
                        kind,
                        row,
                        "postal_code",
                        "Postleitzahl enthält führende oder abschließende Leerzeichen.",
                        Severity.warning,
                        {"reason": "leading_or_trailing_whitespace"},
                    )
    elif rule in {"event_without_dates", "event_without_location"}:
        for row in sources.rows["event"]:
            result.covered.add(("event", entity_key("event", row)))
            if dates.get(str(row["uuid"])):
                continue
            severity = (
                Severity.error
                if row["release_status"] in {"released", "rescheduled"}
                else Severity.warning
            )
            if rule == "event_without_dates":
                emit("event", row, "event_dates", "Event hat keine Termine.", severity)
            elif row["venue_uuid"] is None and not valid_online(row["online_link"]):
                emit(
                    "event",
                    row,
                    "venue_uuid",
                    "Event ohne Termine hat keinen Ort und keine gültige Online-Alternative.",
                    severity,
                )
    elif rule in {"event_date_without_location", "event_date_space_venue_mismatch"}:
        for row in sources.rows["event_date"]:
            result.covered.add(("event_date", entity_key("event_date", row)))
            event = events.get(str(row["event_uuid"]), {})

            venue, space = effective_location(row, event)

            severity = (
                Severity.error if relevance("event_date", row)["published"] else Severity.warning
            )
            if (
                rule == "event_date_without_location"
                and venue is None
                and not valid_online(event.get("online_link"))
            ):
                emit(
                    "event_date",
                    row,
                    "venue_uuid",
                    "Termin ohne wirksamen Ort und ohne gültige Online-Alternative.",
                    severity,
                )
            if rule == "event_date_space_venue_mismatch" and venue and space:
                actual = spaces.get(str(space))
                if actual and actual["venue_uuid"] != venue:
                    emit(
                        "event_date",
                        row,
                        "space_uuid",
                        "Raum gehört nicht zum wirksamen Venue der öffentlichen Projektion.",
                        Severity.error,
                        {
                            "effective_venue": str(venue),
                            "effective_space": str(space),
                            "inheritance": "event_date_location_override",
                        },
                    )
    elif rule in {"venue_missing_logo", "organization_missing_logo"}:
        kind = "venue" if rule == "venue_missing_logo" else "organization"
        images = scan_context.indexes["image"]
        with_logo = {
            str(link["context_uuid"])
            for link in sources.rows["image_link"]
            if link["context"] == kind
            and link["identifier"] == "main_logo"
            and str(link["pluto_image_uuid"]) in images
        }
        for row in sources.rows[kind]:
            key = entity_key(kind, row)
            result.covered.add((kind, key))
            if key not in with_logo:
                emit(
                    kind,
                    row,
                    "main_logo",
                    "Ort hat kein Hauptlogo."
                    if kind == "venue"
                    else "Organisation hat kein Hauptlogo.",
                    metadata={"expected_identifier": "main_logo"},
                )
    elif rule == "logo_unsupported_format":
        # Cover the owners even when a logo link was removed, so old variants resolve.
        targets = {"venue": venues, "organization": orgs}
        for kind, index in targets.items():
            result.covered.update((kind, key) for key in index)
        for link in sources.rows["image_link"]:
            kind, identifier = link["context"], link["identifier"]
            if kind not in targets or identifier not in LOGO_IDENTIFIERS:
                continue
            target = targets[kind].get(str(link["context_uuid"]))
            image = scan_context.indexes["image"].get(str(link["pluto_image_uuid"]))
            if target is None or image is None:
                continue
            mime_type = image.get("mime_type")
            normalized_mime_type = mime_type.strip().lower() if mime_type else ""
            if normalized_mime_type and normalized_mime_type not in LOGO_MIME_TYPES:
                emit(
                    kind,
                    target,
                    f"{identifier}.mime_type",
                    "Logo verwendet kein PNG- oder WebP-Format.",
                    Severity.info,
                    {
                        "identifier": identifier,
                        "mime_type": mime_type,
                        "allowed_mime_types": list(LOGO_MIME_TYPES),
                        "image_uuid": str(image["uuid"]),
                    },
                )
    elif rule.startswith("image_link_"):
        images = scan_context.indexes["image"]
        targets = {"organization": orgs, "venue": venues, "event": events}
        for row in sources.rows["image_link"]:
            kind = "image_link"
            context = row["context"]
            # Portal handlers use portal, while dev DDL exports portal2. No guessed target table.
            if rule == "image_link_missing_target" and context not in targets:
                continue
            result.covered.add((kind, entity_key(kind, row)))
            if rule == "image_link_without_image" and str(row["pluto_image_uuid"]) not in images:
                emit(kind, row, "pluto_image_uuid", "Bildverknüpfung ohne Bild.", Severity.error)
            elif rule == "image_link_unknown_context" and context not in IMAGE_IDENTIFIERS:
                emit(kind, row, "context", "Unbekannter Bildkontext.")
            elif (
                rule == "image_link_invalid_identifier"
                and context in IMAGE_IDENTIFIERS
                and row["identifier"] not in IMAGE_IDENTIFIERS[context]
            ):
                emit(kind, row, "identifier", "Ungültiger Identifier für diesen Bildkontext.")
            elif (
                rule == "image_link_missing_target"
                and str(row["context_uuid"]) not in targets[context]
            ):
                emit(kind, row, "context_uuid", "Ziel der Bildverknüpfung fehlt.", Severity.error)
    elif rule == "image_orphaned_upload":
        linked = {str(row["pluto_image_uuid"]) for row in sources.rows["image_link"]}
        if settings.uranus_timestamp_timezone is None:
            raise ValueError("Source timezone unconfigured")
        for row in sources.rows["image"]:
            result.covered.add(("image", entity_key("image", row)))
            stamp = row["created_at"]
            if (
                stamp is not None
                and str(row["uuid"]) not in linked
                and stamp.replace(tzinfo=ZoneInfo(settings.uranus_timestamp_timezone))
                < now - timedelta(hours=settings.image_orphan_grace_hours)
            ):
                emit(
                    "image",
                    row,
                    "usage",
                    "Upload nach Schonfrist ohne Bildverknüpfung.",
                    Severity.info,
                )
    else:
        raise ValueError("Unknown rule")
    return result
