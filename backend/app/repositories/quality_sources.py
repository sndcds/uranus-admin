"""Explicit source columns only; intentionally no ORM/domain write model or projections."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

SOURCE_QUERIES = {
    "organization": "SELECT uuid, name, street, house_number, address_addition, postal_code, "
    "city, country, state, (point IS NULL OR ST_IsEmpty(point)) AS point_missing, "
    "web_link, contact_email FROM uranus.organization",
    "venue": "SELECT uuid, name, org_uuid, street, house_number, postal_code, city, country, "
    "state, osm_id, (point IS NULL OR ST_IsEmpty(point)) AS point_missing, "
    "web_link, ticket_link, contact_email FROM uranus.venue",
    "space": "SELECT uuid, name, venue_uuid, web_link, total_capacity, seating_capacity, "
    "area_sqm FROM uranus.space",
    "event": "SELECT uuid, title AS name, org_uuid, venue_uuid, space_uuid, release_status::text, "
    "source_link, online_link, ticket_link, registration_link, registration_email, "
    "registration_phone, min_price, max_price, currency, price_type::text, "
    "description, categories, languages FROM uranus.event",
    "event_date": "SELECT uuid, event_uuid, venue_uuid, space_uuid, release_status::text, "
    "start_date, start_time, end_date, end_time, all_day, ticket_link FROM uranus.event_date",
    "event_link": "SELECT id, event_uuid, type, url FROM uranus.event_link",
    "event_type_link": "SELECT event_uuid, type_id, genre_id FROM uranus.event_type_link",
    "event_category": "SELECT DISTINCT category_id FROM uranus.event_category",
    "event_type": "SELECT DISTINCT type_id FROM uranus.event_type",
    "genre_type": "SELECT DISTINCT genre_id FROM uranus.genre_type",
    "language": "SELECT DISTINCT code_iso_639_1 FROM uranus.language",
    "link_type": "SELECT key FROM uranus.link_type",
    "team_membership": "SELECT org_uuid, user_uuid, has_joined, "
    "(accept_token IS NOT NULL AND btrim(accept_token) <> '') AS accept_token_present "
    "FROM uranus.organization_member_link",
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


# Fixed predicates for bounded pre-send revalidation; ordinary quality scans retain
# the existing bulk snapshot. No query per finding/event.
ORGANIZATION_SCOPE = {
    "organization": "uuid = :organization_id",
    "venue": "org_uuid = :organization_id",
    "space": "venue_uuid IN (SELECT uuid FROM uranus.venue WHERE org_uuid=:organization_id)",
    "event": "org_uuid = :organization_id",
    "event_date": "event_uuid IN (SELECT uuid FROM uranus.event WHERE org_uuid=:organization_id)",
    "event_link": "event_uuid IN (SELECT uuid FROM uranus.event WHERE org_uuid=:organization_id)",
    "event_type_link": "event_uuid IN "
    "(SELECT uuid FROM uranus.event WHERE org_uuid=:organization_id)",
    "team_membership": "org_uuid = :organization_id",
    "event_category": "TRUE",
    "event_type": "TRUE",
    "genre_type": "TRUE",
    "language": "TRUE",
    "link_type": "TRUE",
    "license": "FALSE",
    "image_link": "(context='organization' AND context_uuid=:organization_id) OR "
    "(context='venue' AND context_uuid IN "
    "(SELECT uuid FROM uranus.venue WHERE org_uuid=:organization_id)) OR "
    "(context='event' AND context_uuid IN "
    "(SELECT uuid FROM uranus.event WHERE org_uuid=:organization_id))",
}
ORGANIZATION_SCOPE["image"] = (
    "uuid IN (SELECT pluto_image_uuid FROM uranus.pluto_image_link WHERE "
    + ORGANIZATION_SCOPE["image_link"]
    + ")"
)


async def load_sources(connection: AsyncConnection, organization_id: UUID | None = None) -> Sources:
    rows = {}
    for kind, sql in SOURCE_QUERIES.items():
        if organization_id is not None:
            sql += " WHERE " + ORGANIZATION_SCOPE[kind]
        rows[kind] = [
            dict(row)
            for row in (
                await connection.execute(text(sql), {"organization_id": organization_id})
            ).mappings()
        ]
    return Sources(rows)
