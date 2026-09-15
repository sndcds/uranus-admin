import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

from app.config import Settings
from app.repositories.quality_sources import Sources
from app.schemas.action import Action
from app.schemas.finding import Finding, Severity
from app.services.quality.priority import priority_details
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
CORE_RULES = (
    "url_syntax",
    "event_without_dates",
    "event_date_without_location",
    "event_without_location",
    "event_date_space_venue_mismatch",
    "image_link_without_image",
    "image_link_unknown_context",
    "image_link_invalid_identifier",
    "image_link_missing_target",
    "image_orphaned_upload",
)


@dataclass
class RuleResult:
    rule: str
    findings: list[Finding] = field(default_factory=list)
    covered: set[tuple[str, str]] = field(default_factory=set)
    success: bool = True


def entity_key(kind: str, row: dict[str, Any]) -> str:
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


class QualityContext:
    """One immutable source snapshot's indexes and relevance aggregates, built in O(rows)."""

    def __init__(self, sources: Sources, settings: Settings, now: datetime) -> None:
        self.indexes = {
            kind: sources.index(kind)
            for kind in ("organization", "venue", "space", "event", "image")
        }
        self.dates_by_event: dict[str, list[dict[str, Any]]] = {}
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
            upcoming = date["start_date"] > local.date() or (
                date["start_date"] == local.date()
                and (
                    date["all_day"]
                    or date["start_time"] is None
                    or date["start_time"] >= local.time().replace(tzinfo=None)
                )
            )
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
            for kind, key in (
                ("event", event_key),
                ("venue", str(date["venue_uuid"] or parent.get("venue_uuid"))),
                ("space", str(date["space_uuid"] or parent.get("space_uuid"))),
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

    if rule == "url_syntax":
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
            venue = row["venue_uuid"] or event.get("venue_uuid")
            space = row["space_uuid"] or event.get("space_uuid")
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
                            "inheritance": "public_projection_coalesce",
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
