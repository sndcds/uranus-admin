"""Generate synthetic browser fixtures with the real renderer, never a second HTML template.

Run from backend: uv run python -m tests.generate_notification_previews
These are browser inputs for structural/computed-style assertions, not golden snapshots.
"""

import json
from pathlib import Path
from uuid import UUID

from app.config import Settings
from app.schemas.notifications import NotificationPayload
from app.services.notifications.rendering import render


def main() -> None:
    settings = Settings(_env_file=None, app_env="test", notifications_delivery_enabled=False)
    payload = NotificationPayload(
        organization_name="Kulturverein",
        entity_name="Kulturabend",
        entity_type="event",
        entity_key="10000000-0000-4000-8000-000000000021",
        internal_action_path="/events/10000000-0000-4000-8000-000000000021",
        external_action_url=(
            "https://app.kulturbytes.de/admin/event/10000000-0000-4000-8000-000000000021"
        ),
        event_status="draft",
        next_date="2026-09-30",
        days_until=12,
        stage=1,
    )
    variants = {
        "action": [payload],
        "guidance": [payload.model_copy(update={"external_action_url": None})],
        "digest": [
            payload.model_copy(update={"rule": "event_without_dates", "priority": "urgent"}),
            payload.model_copy(update={"rule": "url_syntax", "field": "ticket_link"}),
            payload.model_copy(
                update={
                    "rule": "venue_missing_logo",
                    "entity_type": "venue",
                    "entity_key": "10000000-0000-4000-8000-000000000022",
                    "entity_name": "Kulturhaus" * 30,
                    "external_action_url": None,
                }
            ),
        ],
    }
    output = {
        locale: {
            name: render(
                items, locale, settings, [UUID("10000000-0000-4000-8000-000000000031")]
            ).model_dump(mode="json")
            for name, items in variants.items()
        }
        for locale in ("de", "da", "en")
    }
    target = (
        Path(__file__).resolve().parents[2] / "frontend/tests/fixtures/notification-previews.json"
    )
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
