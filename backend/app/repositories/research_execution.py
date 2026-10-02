"""Exact, bounded SQL metrics using the shared eligible Research population."""

from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.errors import APIError
from app.repositories.research import (
    eligible_event_ctes,
    images,
    parameters,
    record,
    research_sql,
    search_sql,
)
from app.repositories.research_areas import ResolvedResearchArea
from app.repositories.research_resolution import EVENT_TYPES_SQL, GENRES_SQL
from app.research.semantic_limits import MAX_ELIGIBLE_EVENTS
from app.schemas.research import ResearchRecord
from app.schemas.research_execution import (
    AggregateItem,
    ExecutionFilters,
    ExecutionGrouping,
    ExecutionMetric,
    TaxonomyItem,
    TaxonomyKind,
    TaxonomyResult,
)


async def eligible_event_ids(
    connection: AsyncConnection,
    settings: Settings,
    filters: ExecutionFilters,
    area: ResolvedResearchArea | None,
) -> list[UUID]:
    """Complete hard-eligible population or an explicit error; never a truncated sample."""
    rows = await connection.execute(
        text(f"""{eligible_event_ctes(ids_only=True)}
        SELECT DISTINCT entity_key FROM matched_events
        WHERE (:q='%%' OR entity_key::text IN ({search_sql("event")}))
        ORDER BY entity_key LIMIT :eligibility_probe_limit"""),
        {**parameters(filters, settings, area), "eligibility_probe_limit": MAX_ELIGIBLE_EVENTS + 1},
    )
    identifiers = list(rows.scalars())
    if len(identifiers) > MAX_ELIGIBLE_EVENTS:
        raise APIError(
            422,
            "research_execution_too_broad",
            "Narrow the research request before semantic ranking.",
        )
    return identifiers


async def count_selection(
    connection: AsyncConnection,
    settings: Settings,
    filters: ExecutionFilters,
    metric: ExecutionMetric,
    area: ResolvedResearchArea | None,
) -> int:
    occurrences = metric == "occurrence_count"
    sql = research_sql(occurrences=occurrences)
    projection = "count(DISTINCT date_key)" if occurrences else "count(*)"
    return int(
        (
            await connection.execute(
                text(f"SELECT {projection} FROM ({sql}) selected"),
                parameters(filters, settings, area),
            )
        ).scalar_one()
    )


def grouping_sql(group_by: ExecutionGrouping) -> tuple[str, str, str]:
    return {
        "event": ("selected.entity_key::text", "selected.name", ""),
        "venue": ("venue_id::text", "venue_name", ""),
        "organization": ("organization_id::text", "organization_name", ""),
        "category": (
            "category->>'id'",
            "category->>'name'",
            "CROSS JOIN LATERAL jsonb_array_elements(categories) category",
        ),
        "genre": (
            "taxonomy.id",
            "taxonomy.label",
            f"JOIN uranus.event_type_link l ON l.event_uuid=selected.entity_key "
            f"JOIN ({GENRES_SQL}) taxonomy ON taxonomy.id=l.type_id::text||':'||l.genre_id::text "
            "AND (cardinality(CAST(:event_type_ids AS integer[]))=0 "
            "OR l.type_id=ANY(CAST(:event_type_ids AS integer[])))",
        ),
        "event_type": (
            "taxonomy.id",
            "taxonomy.label",
            f"JOIN uranus.event_type_link l ON l.event_uuid=selected.entity_key "
            f"JOIN ({EVENT_TYPES_SQL}) taxonomy ON taxonomy.id=l.type_id::text",
        ),
    }[group_by]


async def aggregate_selection(
    connection: AsyncConnection,
    settings: Settings,
    filters: ExecutionFilters,
    metric: ExecutionMetric,
    group_by: ExecutionGrouping,
    area: ResolvedResearchArea | None,
    ordering: Literal["asc", "desc"] = "desc",
    limit: int = 20,
) -> list[AggregateItem]:
    if group_by == "event" and (metric != "occurrence_count" or filters.entity_type != "event"):
        raise ValueError("event_grouping_requires_event_occurrences")
    # All matching occurrences, including effective venue overrides, not one date/event.
    sql = research_sql(occurrences=True)
    params = parameters(filters.model_copy(update={"entity_type": "event"}), settings, area)
    count = {
        "event_count": "entity_key",
        "occurrence_count": "date_key",
        "venue_count": "venue_id",
        "organization_count": "organization_id",
    }[metric]
    key, name, join = grouping_sql(group_by)
    direction = {"asc": "ASC", "desc": "DESC"}[ordering]
    params["aggregate_limit"] = limit
    rows = (
        await connection.execute(
            text(f"""WITH selected AS ({sql})
        SELECT {key} key,{name} name,count(DISTINCT {count}) value
        FROM selected {join} WHERE {key} IS NOT NULL
        GROUP BY {key},{name}
        ORDER BY value {direction},lower({name}) COLLATE "C",({key}) COLLATE "C"
        LIMIT :aggregate_limit"""),
            params,
        )
    ).mappings()
    return [AggregateItem.model_validate(dict(r)) for r in rows]


async def chronological_records(
    connection: AsyncConnection,
    settings: Settings,
    filters: ExecutionFilters,
    area: ResolvedResearchArea | None,
    ordering: Literal["asc", "desc"],
    limit: int,
) -> list[ResearchRecord]:
    """Rank matching occurrences, then distinct events; never the UI representative date.

    Unknown dates and undated events cannot establish a chronological position.
    All eligibility and occurrence context come from the shared source projection.
    """
    if filters.entity_type != "event" or not 1 <= limit <= 20:
        raise ValueError("invalid_chronological_selection")
    direction = {"asc": "ASC", "desc": "DESC"}[ordering]
    order = (
        f"start_date {direction},start_time {direction} NULLS LAST,"
        f"date_key {direction},entity_key {direction}"
    )
    columns = """entity_type,entity_key,name,description,status,categories,language,
        start_date,start_time,end_date,end_time,all_day,organization_id,organization_name,
        venue_id,venue_name,space_id,space_name,city,address,latitude,longitude,event_count,
        source_url,created_at,modified_at,date_key"""
    rows = (
        await connection.execute(
            text(f"""WITH selected AS ({research_sql(occurrences=True)}), ranked AS (
                SELECT {columns},row_number() OVER (
                    PARTITION BY entity_key ORDER BY {order}) occurrence_rank
                FROM selected WHERE date_key IS NOT NULL AND start_date IS NOT NULL
            ) SELECT {columns} FROM ranked WHERE occurrence_rank=1
            ORDER BY {order} LIMIT :chronological_limit"""),
            {**parameters(filters, settings, area), "chronological_limit": limit},
        )
    ).mappings()
    items = [record(row) for row in rows]
    await images(connection, items, settings)
    return items


async def taxonomy_selection(
    connection: AsyncConnection,
    settings: Settings,
    filters: ExecutionFilters,
    taxonomy: TaxonomyKind,
    area: ResolvedResearchArea | None,
    limit: int = 20,
    ordering: Literal["asc", "desc"] = "asc",
) -> TaxonomyResult:
    """Used taxonomy values, counted over the complete matching public population."""
    key, name, join = grouping_sql(taxonomy)
    direction = {"asc": "ASC", "desc": "DESC"}[ordering]
    rows = list(
        (
            await connection.execute(
                text(f"""
        WITH selected AS ({research_sql(occurrences=True)}), grouped AS (
            SELECT {key} key, {name} name, count(DISTINCT entity_key) event_count
            FROM selected {join} WHERE {key} IS NOT NULL
            GROUP BY {key}, {name}
        ) SELECT key,name,event_count,count(*) OVER () total FROM grouped
        ORDER BY lower(name) COLLATE "C" {direction},key COLLATE "C"
        LIMIT :taxonomy_limit
    """),
                {**parameters(filters, settings, area), "taxonomy_limit": limit},
            )
        ).mappings()
    )
    return TaxonomyResult(
        taxonomy=taxonomy,
        total=rows[0]["total"] if rows else 0,
        items=[
            TaxonomyItem(key=r["key"], name=r["name"], event_count=r["event_count"]) for r in rows
        ],
    )


async def spatial_records(
    connection: AsyncConnection,
    settings: Settings,
    filters: ExecutionFilters,
    area: ResolvedResearchArea | None,
    metric: Literal["longitude", "latitude"],
    ordering: Literal["asc", "desc"],
    limit: int,
) -> list[ResearchRecord]:
    coordinate = {"longitude": "longitude", "latitude": "latitude"}[metric]
    direction = {"asc": "ASC", "desc": "DESC"}[ordering]
    if filters.entity_type not in {"event", "venue"} or not 1 <= limit <= 20:
        raise ValueError("invalid_spatial_selection")
    columns = """entity_type,entity_key,name,description,status,categories,language,
        start_date,start_time,end_date,end_time,all_day,organization_id,organization_name,
        venue_id,venue_name,space_id,space_name,city,address,latitude,longitude,event_count,
        source_url,created_at,modified_at"""
    occurrence = filters.entity_type == "event"
    tie = "date_key NULLS LAST," if occurrence else ""
    order = f"{coordinate} {direction},{tie}entity_key"
    rows = (
        await connection.execute(
            text(f"""
        WITH selected AS ({research_sql(occurrences=occurrence)}), ranked AS (
            SELECT {columns}, {"date_key," if occurrence else ""}
                row_number() OVER (PARTITION BY entity_key ORDER BY {order}) rank
            FROM selected WHERE longitude BETWEEN -180 AND 180 AND latitude BETWEEN -90 AND 90
        ) SELECT {columns} FROM ranked WHERE rank=1
        ORDER BY {order} LIMIT :spatial_limit
    """),
            {**parameters(filters, settings, area), "spatial_limit": limit},
        )
    ).mappings()
    items = [record(row) for row in rows]
    await images(connection, items, settings)
    return items
