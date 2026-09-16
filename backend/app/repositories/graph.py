"""Bounded breadth-first exploration. All identifiers and relations are source constants."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.errors import APIError
from app.repositories.activity import ENTITY_ACTIVITY_SQL
from app.repositories.activity_previews import activity_previews
from app.repositories.location import EFFECTIVE_SPACE_SQL, EFFECTIVE_VENUE_SQL
from app.schemas.action import Action
from app.schemas.graph import (
    GraphEdge,
    GraphFilters,
    GraphNode,
    GraphResponse,
    GraphRoot,
    GraphSearchFilters,
    GraphSearchResponse,
)

MAX_NODES = 100
MAX_EDGES = 200
TYPES = ("organization", "venue", "space", "event", "event_date", "user")
# Reuse the explicit safe Activity name/status projection. PostgreSQL can inline this CTE.
ENTITY_SQL = " UNION ALL ".join(ENTITY_ACTIVITY_SQL.values())
NODES_SQL = f"SELECT * FROM ({ENTITY_SQL}) a WHERE entity_type = ANY(:types)"
SOURCE_ALIASES = {
    "organization": "o",
    "venue": "v",
    "space": "s",
    "event": "e",
    "event_date": "d",
    "user": "u",
}
LABELS = {
    "organization_has_venue": "Betreibt",
    "venue_has_space": "Hat Raum",
    "organization_has_event": "Organisiert",
    "event_has_date": "Hat Termin",
    "event_uses_venue": "Standardort",
    "event_uses_space": "Standardraum",
    "event_date_uses_venue": "Findet statt in",
    "event_date_uses_space": "Nutzt Raum",
    "user_member_of_organization": "Mitglied von",
    "user_invited_to_organization": "Eingeladen zu",
    "organization_partner_request": "Partneranfrage",
    "organization_partner_of": "Partner von",
}
# Each tuple is a fixed source clause and two endpoint expressions. Each branch restricts
# its work to the current frontier, then returns at most 201 candidates, never all records.
RELATIONS = [
    (
        "organization_has_venue",
        "organization",
        "v.org_uuid",
        "venue",
        "v.uuid",
        "uranus.venue v",
        "TRUE",
    ),
    ("venue_has_space", "venue", "s.venue_uuid", "space", "s.uuid", "uranus.space s", "TRUE"),
    (
        "organization_has_event",
        "organization",
        "e.org_uuid",
        "event",
        "e.uuid",
        "uranus.event e",
        "TRUE",
    ),
    (
        "event_has_date",
        "event",
        "d.event_uuid",
        "event_date",
        "d.uuid",
        "uranus.event_date d",
        "TRUE",
    ),
    ("event_uses_venue", "event", "e.uuid", "venue", "e.venue_uuid", "uranus.event e", "TRUE"),
    ("event_uses_space", "event", "e.uuid", "space", "e.space_uuid", "uranus.event e", "TRUE"),
    (
        "event_date_uses_venue",
        "event_date",
        "d.uuid",
        "venue",
        EFFECTIVE_VENUE_SQL,
        "uranus.event_date d JOIN uranus.event e ON e.uuid=d.event_uuid",
        "TRUE",
    ),
    (
        "event_date_uses_space",
        "event_date",
        "d.uuid",
        "space",
        EFFECTIVE_SPACE_SQL,
        "uranus.event_date d JOIN uranus.event e ON e.uuid=d.event_uuid",
        "TRUE",
    ),
    (
        "user_member_of_organization",
        "user",
        "m.user_uuid",
        "organization",
        "m.org_uuid",
        "uranus.organization_member_link m",
        "m.has_joined IS TRUE",
    ),
    (
        "user_invited_to_organization",
        "user",
        "m.user_uuid",
        "organization",
        "m.org_uuid",
        "uranus.organization_member_link m",
        "m.has_joined IS FALSE",
    ),
    (
        "organization_partner_request",
        "organization",
        "p.from_org_uuid",
        "organization",
        "p.to_org_uuid",
        "uranus.organization_partner_request p",
        "p.status='pending'",
    ),
    (
        "organization_partner_of",
        "organization",
        "p.from_org_uuid",
        "organization",
        "p.to_org_uuid",
        "uranus.organization_partner_request p",
        "p.status='accepted' AND EXISTS (SELECT 1 FROM uranus.organization_access_grants g "
        "WHERE g.src_org_uuid=p.to_org_uuid AND g.dst_org_uuid=p.from_org_uuid)",
    ),
]


def adjacency_sql() -> str:
    branches = []
    for kind, src_type, src, dst_type, dst, table, condition in RELATIONS:
        branches.append(f"""(SELECT '{kind}' type,
            '{src_type}:'||({src})::text source, '{dst_type}:'||({dst})::text target
            FROM {table} WHERE {condition} AND ({src}) IS NOT NULL AND ({dst}) IS NOT NULL
            AND (CAST(:relation AS text) IS NULL OR :relation='{kind}')
            AND (({src}) = ANY(CAST(:{src_type} AS uuid[]))
                 OR ({dst}) = ANY(CAST(:{dst_type} AS uuid[])))
            ORDER BY source,target LIMIT :limit)""")
    return (
        "SELECT DISTINCT * FROM ("
        + " UNION ALL ".join(branches)
        + (") r ORDER BY type,source,target LIMIT :limit")
    )


ADJACENCY_SQL = adjacency_sql()


def node(row: dict[str, Any]) -> GraphNode:
    kind, key = row["entity_type"], row["entity_key"]
    return GraphNode(
        id=f"{kind}:{key}",
        type=kind,
        key=key,
        label=row["entity_name"],
        status=row["status"],
        admin_url=Action(route="activity", entity_type=kind, entity_key=key).href,
    )


async def search(connection: AsyncConnection, filters: GraphSearchFilters) -> GraphSearchResponse:
    # Literal substring matching: % and _ in names are not wildcard instructions.
    query = filters.q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = (
        await connection.execute(
            text(f"""
        SELECT entity_type,entity_key,entity_name,status FROM ({NODES_SQL}) a
        WHERE (entity_name ILIKE :q OR entity_key ILIKE :q)
        AND (CAST(:org AS uuid) IS NULL OR organization_id=:org
          OR (entity_type='user' AND EXISTS (
            SELECT 1 FROM uranus.organization_member_link m
            WHERE m.user_uuid::text=a.entity_key AND m.org_uuid=:org)))
        ORDER BY lower(entity_name),entity_type,entity_key LIMIT :limit
    """),
            {
                "types": [filters.entity_type] if filters.entity_type else list(TYPES),
                "q": f"%{query}%",
                "org": filters.organization_id,
                "limit": filters.limit,
            },
        )
    ).mappings()
    return GraphSearchResponse(items=[node(dict(row)) for row in rows])


async def load_nodes(connection: AsyncConnection, ids: set[str]) -> dict[str, GraphNode]:
    if not ids:
        return {}
    grouped = {
        kind: sorted(
            identity.split(":", 1)[1] for identity in ids if identity.startswith(f"{kind}:")
        )
        for kind in TYPES
    }
    # Primary UUID predicates are pushed into each fixed entity projection. No concatenated
    # identity scan or entire source-table hydration is needed to resolve a small frontier.
    branches = [
        f"{ENTITY_ACTIVITY_SQL[kind]} WHERE {SOURCE_ALIASES[kind]}.uuid "
        f"= ANY(CAST(:{kind} AS uuid[]))"
        for kind in TYPES
        if grouped[kind]
    ]
    query = (
        "SELECT * FROM ("
        + " UNION ALL ".join(branches)
        + ") n(entity_type,entity_key,entity_name,organization_id,"
        "organization_name,created_at,status) "
        "ORDER BY entity_type,entity_key"
    )
    rows = (await connection.execute(text(query), grouped)).mappings()
    return {item.id: item for item in (node(dict(row)) for row in rows)}


async def explore(
    connection: AsyncConnection,
    settings: Settings,
    filters: GraphFilters,
) -> GraphResponse:
    root_id = f"{filters.root_type}:{filters.root_key}"
    nodes = await load_nodes(connection, {root_id})
    if not nodes:
        raise APIError(404, "not_found", "Graph root not found.")
    frontier = {root_id}
    visited: set[str] = set()
    edges: dict[str, GraphEdge] = {}
    truncated = False
    for _ in range(filters.depth):
        if not frontier:
            break
        params: dict[str, Any] = {kind: [] for kind in TYPES}
        for identity in sorted(frontier):
            kind, key = identity.split(":", 1)
            params[kind].append(key)
        params.update(relation=filters.relation_type, limit=MAX_EDGES + 1)
        rows = list((await connection.execute(text(ADJACENCY_SQL), params)).mappings())
        truncated |= len(rows) > MAX_EDGES
        candidates = await load_nodes(
            connection,
            {str(row[end]) for row in rows for end in ("source", "target")} - nodes.keys(),
        )
        available = nodes | candidates
        next_frontier: set[str] = set()
        for row in rows:
            source, target, kind = row["source"], row["target"], row["type"]
            identity = f"{kind}:{source}:{target}"
            if identity in edges or source not in available or target not in available:
                continue
            missing = {source, target} - nodes.keys()
            if len(nodes) + len(missing) > MAX_NODES or len(edges) >= MAX_EDGES:
                truncated = True
                continue
            for key in sorted(missing):
                nodes[key] = available[key]
                next_frontier.add(key)
            edges[identity] = GraphEdge(
                id=identity,
                source=source,
                target=target,
                type=kind,
                label=LABELS[kind],
                direction="undirected" if kind == "organization_partner_of" else "directed",
            )
        visited.update(frontier)
        frontier = next_frontier - visited
    # Reuse established public-link decisions in one batch; never expose preview emails.
    previews = await activity_previews(
        connection,
        settings,
        [{"entity_type": n.type, "entity_key": str(n.key)} for n in nodes.values()],
        datetime.now(UTC),
    )
    for item in nodes.values():
        preview = previews.get((item.type, str(item.key)), {})
        item.public_url = preview.get("public_url")
        item.subtitle = preview.get("subtitle")
    return GraphResponse(
        root=GraphRoot(type=filters.root_type, key=filters.root_key),
        nodes=sorted(nodes.values(), key=lambda n: n.id),
        edges=sorted(edges.values(), key=lambda e: e.id),
        truncated=truncated,
        max_nodes=MAX_NODES,
        max_edges=MAX_EDGES,
    )
