"""Bounded, read-only venue/organization projections with canonical public event gates.

Source fields verified against local Uranus 106ab24af97854e988f3c1b6c72b8ae2e9c1680f
DDL and public get-venue/get-venues SQL; not a claim about a deployed schema.
"""

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.repositories.location import EFFECTIVE_VENUE_SQL
from app.repositories.research import DATE_STATUS, PUBLIC
from app.repositories.vector_events import PUBLIC_EVENT, area_memberships
from app.research.semantic_contracts import SemanticDocument
from app.research.semantic_documents import organization_document, venue_document

PUBLIC_VENUE_EVENT = f"""EXISTS (SELECT 1 FROM uranus.event_date d
    JOIN uranus.event e ON e.uuid=d.event_uuid WHERE {EFFECTIVE_VENUE_SQL}=v.uuid
    AND e.release_status::text IN {PUBLIC} AND {DATE_STATUS} IN {PUBLIC})"""
VENUE_SQL = f"""SELECT v.uuid entity_id,v.org_uuid organization_id,o.name organization_name,
    v.name,v.description,v.summary,v.type,v.scope,v.accessibility_summary,v.opening_hours,
    v.street,v.house_number,v.postal_code,v.city,v.country,v.web_link,v.ticket_link,v.ticket_info,
    ST_X(v.point) longitude,ST_Y(v.point) latitude,
    v.modified_at AT TIME ZONE :source_tz source_updated_at,
    {PUBLIC_VENUE_EVENT} has_public_event
    FROM uranus.venue v JOIN uranus.organization o ON o.uuid=v.org_uuid
    ORDER BY v.uuid LIMIT 10001"""
PUBLIC_ORGANIZATION = (
    f"EXISTS (SELECT 1 FROM uranus.event e WHERE e.org_uuid=o.uuid AND {PUBLIC_EVENT})"
)
ORGANIZATION_SQL = f"""SELECT o.uuid entity_id,o.name,o.description,o.web_link,
    ST_X(o.point) longitude,ST_Y(o.point) latitude,
    o.modified_at AT TIME ZONE :source_tz source_updated_at
    FROM uranus.organization o WHERE {PUBLIC_ORGANIZATION}
    ORDER BY o.uuid LIMIT :limit"""
ACTIVITY_SQL = f"""SELECT DISTINCT e.org_uuid organization_id,v.uuid venue_id,
    ST_X(v.point) longitude,ST_Y(v.point) latitude
    FROM uranus.event_date d JOIN uranus.event e ON e.uuid=d.event_uuid
    JOIN uranus.venue v ON v.uuid={EFFECTIVE_VENUE_SQL}
    WHERE e.org_uuid=ANY(CAST(:ids AS uuid[])) AND e.release_status::text IN {PUBLIC}
        AND {DATE_STATUS} IN {PUBLIC}
    UNION
    SELECT v.org_uuid organization_id,v.uuid venue_id,ST_X(v.point) longitude,ST_Y(v.point) latitude
    FROM uranus.venue v WHERE v.org_uuid=ANY(CAST(:ids AS uuid[]))
    ORDER BY organization_id,venue_id LIMIT 100001"""


def validate_snapshot(settings: Settings, limit: int | None) -> None:
    if limit is not None and not 1 <= limit <= 10000:
        raise ValueError("invalid_entity_limit")
    if not settings.uranus_timestamp_timezone:
        raise ValueError("source_timezone_required")


def check_corpus(documents: list[SemanticDocument]) -> None:
    if sum(len(d.model_dump_json().encode()) for d in documents) > 64 * 1024 * 1024:
        raise ValueError("semantic_corpus_limit")


async def extract_venues(
    connection: AsyncConnection,
    admin: AsyncConnection | None,
    settings: Settings,
    now: datetime,
    limit: int | None = None,
) -> tuple[list[SemanticDocument], int]:
    validate_snapshot(settings, limit)
    rows = [
        dict(r)
        for r in (
            await connection.execute(
                text(VENUE_SQL), {"source_tz": settings.uranus_timestamp_timezone}
            )
        ).mappings()
    ]
    if len(rows) > 10000:
        raise ValueError("venue_snapshot_limit")
    available, memberships = await area_memberships(
        admin,
        [
            {"venue_id": r["entity_id"], "latitude": r["latitude"], "longitude": r["longitude"]}
            for r in rows
        ],
    )
    # Matches Research's no-event-filter area projection, without treating scope as release.
    selected = [r for r in rows if r["has_public_event"] or memberships.get(str(r["entity_id"]))]
    documents = [
        venue_document(r, memberships.get(str(r["entity_id"]), []), available)
        for r in selected[:limit]
    ]
    check_corpus(documents)
    return documents, len(selected)


async def extract_organizations(
    connection: AsyncConnection,
    admin: AsyncConnection | None,
    settings: Settings,
    now: datetime,
    limit: int | None = None,
) -> tuple[list[SemanticDocument], int]:
    validate_snapshot(settings, limit)
    total = int(
        (
            await connection.execute(
                text(f"SELECT count(*) FROM uranus.organization o WHERE {PUBLIC_ORGANIZATION}")
            )
        ).scalar_one()
    )
    if total > 10000 and limit is None:
        raise ValueError("organization_snapshot_limit")
    rows = [
        dict(r)
        for r in (
            await connection.execute(
                text(ORGANIZATION_SQL),
                {"source_tz": settings.uranus_timestamp_timezone, "limit": limit or 10000},
            )
        ).mappings()
    ]
    activity = [
        dict(r)
        for r in (
            await connection.execute(text(ACTIVITY_SQL), {"ids": [r["entity_id"] for r in rows]})
        ).mappings()
    ]
    if len(activity) > 100000:
        raise ValueError("organization_activity_limit")
    # Separate lookups prevent equal UUIDs across entity types from aliasing points.
    available, home = await area_memberships(
        admin,
        [
            {"venue_id": r["entity_id"], "latitude": r["latitude"], "longitude": r["longitude"]}
            for r in rows
        ],
    )
    _, memberships = await area_memberships(admin, activity)
    by_org: dict[Any, list[dict[str, str]]] = defaultdict(list)
    for point in activity:
        # An owned venue inside a cached area is itself Research-eligible. Event
        # locations above are gated by public date/event statuses regardless of owner.
        by_org[point["organization_id"]].extend(memberships.get(str(point["venue_id"]), []))
    documents = [
        organization_document(
            r, home.get(str(r["entity_id"]), []), by_org[r["entity_id"]], available
        )
        for r in rows
    ]
    check_corpus(documents)
    return documents, total
