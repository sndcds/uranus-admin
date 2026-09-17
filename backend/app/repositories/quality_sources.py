"""Explicit source columns only; intentionally no ORM/domain write model or projections."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

SOURCE_QUERIES = {
    "organization": "SELECT uuid, name, web_link FROM uranus.organization",
    "venue": "SELECT uuid, name, org_uuid, web_link, ticket_link FROM uranus.venue",
    "space": "SELECT uuid, name, venue_uuid, web_link FROM uranus.space",
    "event": "SELECT uuid, title AS name, org_uuid, venue_uuid, space_uuid, release_status::text, "
    "source_link, online_link, ticket_link, registration_link FROM uranus.event",
    "event_date": "SELECT uuid, event_uuid, venue_uuid, space_uuid, release_status::text, "
    "start_date, start_time, all_day, ticket_link FROM uranus.event_date",
    "event_link": "SELECT id, event_uuid, url FROM uranus.event_link",
    "license": "SELECT key, url FROM uranus.license",
    "image": "SELECT uuid, created_at, mime_type FROM uranus.pluto_image",
    "image_link": "SELECT context, context_uuid, identifier, pluto_image_uuid "
    "FROM uranus.pluto_image_link",
}


@dataclass
class Sources:
    rows: dict[str, list[dict[str, Any]]]

    def index(self, kind: str) -> dict[str, dict[str, Any]]:
        return {str(row["uuid"]): row for row in self.rows[kind]}


async def load_sources(connection: AsyncConnection) -> Sources:
    rows = {}
    for kind, sql in SOURCE_QUERIES.items():
        rows[kind] = [dict(row) for row in (await connection.execute(text(sql))).mappings()]
    return Sources(rows)
