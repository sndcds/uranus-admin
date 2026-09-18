"""Pure scheduling decisions. Successful delivery history is the reminder clock."""

import copy
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from app.schemas.notifications import NotificationConfig, NotificationRecipient
from app.services.notifications.candidates import semantic_payload
from app.services.notifications.policy import TEMPLATE_VERSION


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def content_version(rows: list[dict[str, Any]]) -> str:
    return fingerprint(
        {
            "template": TEMPLATE_VERSION,
            "items": sorted(
                [(str(r["id"]), semantic_payload(r["payload"])) for r in rows], key=lambda r: r[0]
            ),
        }
    )


def batches(
    rows: list[dict[str, Any]],
    history: list[dict[str, Any]],
    recipient: NotificationRecipient,
    config: NotificationConfig,
    now: datetime,
) -> list[dict[str, Any]]:
    active = [r for r in rows if r["status"] == "active"]
    sent = sorted(
        (
            d
            for d in history
            if d["status"] == "sent"
            and d["recipient"].casefold() == str(recipient.email).casefold()
        ),
        key=lambda d: d["sent_at"],
        reverse=True,
    )
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    anchors: dict[str, str] = {}
    event_kinds: dict[int, str] = {}
    kind_rank = {"initial": 0, "reminder": 1, "escalation": 2}
    for row in active:
        if row["notification_type"] == "quality_finding":
            groups[("digest", 0)].append(row)
            continue
        previous = next((d for d in sent if str(row["id"]) in d["snapshot"]["ids"]), None)
        if previous is None:
            kind = "initial"
        else:
            old = previous["snapshot"]["payloads"][
                previous["snapshot"]["ids"].index(str(row["id"]))
            ]
            if row["payload"].get("episode", 1) > old.get("episode", 1):
                kind = "initial"
            elif row["payload"]["stage"] > old["stage"]:
                kind = "escalation"
            elif config.events.unpublished_upcoming_events.reminder.enabled and now >= previous[
                "sent_at"
            ] + timedelta(days=config.events.unpublished_upcoming_events.reminder.days_after):
                kind = "reminder"
            else:
                continue
        current_stage = row["payload"]["stage"]
        event_kinds[current_stage] = max(
            (event_kinds.get(current_stage, "initial"), kind), key=kind_rank.__getitem__
        )
        groups[("event", current_stage)].append(row)
        anchors[str(row["id"])] = str(previous["id"]) if previous else "initial"
    result = []
    for (family, current_stage), items in groups.items():
        kind = "digest" if family == "digest" else event_kinds[current_stage]
        items.sort(key=lambda r: str(r["id"]))
        version = content_version(items)
        previous = (
            next((d for d in sent if d["delivery_kind"] == "digest"), None)
            if kind == "digest"
            else None
        )
        if previous and previous["snapshot"]["version"] == version:
            continue
        intent = {
            "recipient": str(recipient.email).casefold(),
            "locale": recipient.locale,
            "kind": kind,
            "version": version,
            "anchor": str(previous["id"])
            if previous
            else {str(r["id"]): anchors.get(str(r["id"]), "digest") for r in items},
        }
        result.append(
            {
                "recipient": str(recipient.email),
                "locale": recipient.locale,
                "delivery_kind": kind,
                "message_fingerprint": fingerprint(intent),
                "snapshot": {
                    "version": version,
                    "ids": [str(r["id"]) for r in items],
                    "payloads": [copy.deepcopy(r["payload"]) for r in items],
                },
            }
        )
    return result
