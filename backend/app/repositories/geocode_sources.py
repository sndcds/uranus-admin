"""Explicit authoritative owners; bounded source batches and no admin joins."""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

PROJECTIONS = {
    "organization": "uuid, name, street, house_number, address_addition, "
    "postal_code, city, country, state",
    "venue": "uuid, org_uuid, name, street, house_number, postal_code, "
    "city, country, state, osm_id",
}


async def source_rows(
    connection: AsyncConnection,
    kind: str,
    *,
    ids: list[UUID] | None = None,
    after: UUID | None = None,
) -> list[dict[str, Any]]:
    columns = PROJECTIONS[kind]  # Closed code-owned mapping, never a SQL identifier from HTTP.
    predicate = (
        "uuid = ANY(CAST(:ids AS uuid[]))"
        if ids is not None
        else "(CAST(:after AS uuid) IS NULL OR uuid > CAST(:after AS uuid)) "
        "AND (point IS NULL OR ST_IsEmpty(point))"
    )
    result = await connection.execute(
        text(
            f"SELECT {columns}, (point IS NULL OR ST_IsEmpty(point)) AS point_missing "
            f"FROM uranus.{kind} WHERE {predicate} ORDER BY uuid LIMIT 500"
        ),
        {"ids": ids, "after": after},
    )
    return [
        {**dict(row), "entity_type": kind, "entity_key": row["uuid"]} for row in result.mappings()
    ]


async def lookup_sources(
    connection: AsyncConnection, requests: list[dict[str, Any]]
) -> dict[tuple[str, UUID], dict[str, Any]]:
    result = {}
    for kind in PROJECTIONS:
        ids = list({row["entity_key"] for row in requests if row["entity_type"] == kind})
        if ids:
            for row in await source_rows(connection, kind, ids=ids):
                result[(kind, row["entity_key"])] = row
    return result
