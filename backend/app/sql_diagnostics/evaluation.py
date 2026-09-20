from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.config import Settings
from app.services.quality.core import date_without_location, effective_location
from app.services.quality.rules.v2 import (
    blank,
    date_issues,
    joined_token_present,
    price_without_currency,
)
from app.services.quality.urls import url_problem, valid_online
from app.services.queues import partner_long_pending
from app.sql_diagnostics.models import DiagnosticCheck, DiagnosticEvaluation, StoredFinding
from app.sql_diagnostics.render import json_value


def evaluate(
    finding: StoredFinding, rows: list[dict[str, Any]], settings: Settings, now: datetime
) -> DiagnosticEvaluation:
    if not rows:
        return DiagnosticEvaluation(
            matched=None,
            checks=[],
            message=(
                "Quelldatensatz nicht mehr vorhanden; historische Bewertung bleibt unverändert."
            ),
        )
    if len(rows) != 1:
        raise ValueError("Diagnostic identity must identify one row")
    row = rows[0]
    checks: list[DiagnosticCheck] = []
    rule = finding.rule
    if rule in {"event_date_end_before_start", "event_date_same_day_end_before_start"}:
        matched = bool(list(date_issues(rule, row)))
        start, end = row["start_date"], row["end_date"]
        checks.append(DiagnosticCheck(label="Enddatum vorhanden", value=end is not None))
        if rule == "event_date_end_before_start":
            checks.append(
                DiagnosticCheck(
                    label="Enddatum < Startdatum",
                    value=matched,
                    left=json_value(end),
                    operator="<",
                    right=json_value(start),
                )
            )
        else:
            checks.append(
                DiagnosticCheck(
                    label="Gleiches Datum",
                    value=end == start,
                    left=json_value(end),
                    operator="=",
                    right=json_value(start),
                )
            )
            checks.append(
                DiagnosticCheck(
                    label="Beide Zeiten vorhanden",
                    value=row["start_time"] is not None and row["end_time"] is not None,
                )
            )
            checks.append(
                DiagnosticCheck(
                    label="Endzeit < Startzeit",
                    value=None
                    if row["start_time"] is None or row["end_time"] is None
                    else row["end_time"] < row["start_time"],
                    left=json_value(row["end_time"]),
                    operator="<",
                    right=json_value(row["start_time"]),
                )
            )
    elif rule == "event_date_without_location":
        date_row = {"venue_uuid": row["date_venue_uuid"], "space_uuid": row["date_space_uuid"]}
        event = {
            "venue_uuid": row["event_venue_uuid"],
            "space_uuid": row["event_space_uuid"],
            "online_link": row["online_link"],
        }
        matched = date_without_location(date_row, event)
        checks = [
            DiagnosticCheck(
                label="Wirksames Venue fehlt", value=effective_location(date_row, event)[0] is None
            ),
            DiagnosticCheck(
                label="Keine gültige Online-Alternative (valid_online)",
                value=not valid_online(row["online_link"]),
            ),
        ]
    elif rule == "event_price_without_currency":
        matched = price_without_currency(row)
        checks = [
            DiagnosticCheck(
                label="Mindestens ein Preis gesetzt",
                value=row["min_price"] is not None or row["max_price"] is not None,
            ),
            DiagnosticCheck(label="Währung leer (blank)", value=blank(row["currency"])),
        ]
    elif rule == "venue_missing_location":
        matched = bool(row["point_missing"])
        checks = [DiagnosticCheck(label="point IS NULL OR ST_IsEmpty(point)", value=matched)]
    elif rule == "url_syntax":
        problem = url_problem(row[finding.field])
        matched = problem is not None
        checks = [
            DiagnosticCheck(label="URL-Parser: " + (problem or "kein Syntaxproblem"), value=matched)
        ]
    elif rule == "membership_joined_accept_token_present":
        matched = joined_token_present(row)
        checks = [
            DiagnosticCheck(label="Beigetreten", value=bool(row["has_joined"])),
            DiagnosticCheck(
                label="Annahmetoken vorhanden (nur Boolean)",
                value=bool(row["accept_token_present"]),
            ),
        ]
    elif rule == "partner_long_pending":
        matched = partner_long_pending(row, settings, now)
        created = row["created_at"].replace(
            tzinfo=ZoneInfo(settings.uranus_timestamp_timezone or "UTC")
        )
        threshold = now - timedelta(days=settings.pending_age_days)
        checks = [
            DiagnosticCheck(label="Status pending", value=row["status"] == "pending"),
            DiagnosticCheck(
                label=(
                    f"Älter als {settings.pending_age_days} Tage "
                    f"({settings.uranus_timestamp_timezone})"
                ),
                value=created < threshold,
                left=created.isoformat(),
                operator="<",
                right=threshold.isoformat(),
            ),
        ]
    else:
        raise ValueError("Unregistered evaluation")
    return DiagnosticEvaluation(
        matched=matched,
        checks=checks,
        message="Aktueller Datenstand erfüllt die Regel."
        if matched
        else "Aktueller Datenstand erfüllt die Regel nicht mehr.",
    )
