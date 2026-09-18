"""Recipient routes verified in uranus-dashboard; independent of system-admin routes.

See backend/docs/notifications.md for pinned router/editor/auth evidence. Parent IDs
come exclusively from the existing read-only source snapshot, never from names.
"""

import re
from urllib.parse import urlsplit
from uuid import UUID

from app.config import Settings
from app.repositories.quality_sources import Sources

_UUID = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
ROUTES = {
    "event": re.compile(rf"/admin/event/{_UUID}"),
    "organization": re.compile(rf"/admin/org/{_UUID}/edit"),
    "venue": re.compile(rf"/admin/org/{_UUID}/venue/{_UUID}/edit"),
    "space": re.compile(rf"/admin/org/{_UUID}/venue/{_UUID}/space/{_UUID}/edit"),
}


class RecipientActions:
    def __init__(self, sources: Sources, settings: Settings) -> None:
        self.base = settings.kulturbytes_app_public_base_url
        self.rows = {
            kind: {
                str(row["id" if kind == "event_link" else "uuid"]): row
                for row in sources.rows[kind]
            }
            for kind in (*ROUTES, "event_date", "event_link")
        }

    def url(self, entity: str, key: str, organization_id: UUID) -> str | None:
        row = self.rows.get(entity, {}).get(key)
        if row is None:
            return None
        if entity in {"event_date", "event_link"}:
            return self.url("event", str(row["event_uuid"]), organization_id)
        org = str(organization_id)
        if entity == "organization":
            path = f"/admin/org/{org}/edit" if key == org else None
        elif entity == "event":
            path = f"/admin/event/{key}" if str(row["org_uuid"]) == org else None
        elif entity == "venue":
            path = f"/admin/org/{org}/venue/{key}/edit" if str(row["org_uuid"]) == org else None
        elif entity == "space":
            venue = self.rows["venue"].get(str(row["venue_uuid"]))
            path = (
                f"/admin/org/{org}/venue/{row['venue_uuid']}/space/{key}/edit"
                if venue is not None and str(venue["org_uuid"]) == org
                else None
            )
        else:
            path = None
        if path is None or ROUTES[entity].fullmatch(path) is None:
            return None
        return self.base + path


def recipient_action(url: str | None, entity: str, settings: Settings) -> tuple[str, str] | None:
    """Validate saved snapshots again before rendering. Unsafe URLs become guidance."""
    if not url or any(ord(char) < 33 or ord(char) == 127 for char in url):
        return None
    try:
        parsed = urlsplit(url)
        origin = urlsplit(settings.kulturbytes_app_public_base_url)
        target = "event" if entity in {"event_date", "event_link"} else entity
        route = ROUTES.get(target)
        if (
            parsed.scheme != origin.scheme
            or parsed.netloc != origin.netloc
            or parsed.hostname == "admin.kulturbytes.de"
            or parsed.hostname
            == (urlsplit(settings.admin_public_base_url).hostname or "").rstrip(".")
            or parsed.hostname
            == (urlsplit(settings.auth_public_origin or "").hostname or "").rstrip(".")
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or "?" in url
            or "#" in url
            or route is None
            or route.fullmatch(parsed.path) is None
        ):
            return None
        return url, target
    except ValueError:
        return None
