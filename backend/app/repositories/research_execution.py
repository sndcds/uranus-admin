"""Exact, bounded SQL metrics using the shared eligible Research population."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.errors import APIError
from app.repositories.research import eligible_event_ctes, parameters, research_sql, search_sql
from app.repositories.research_areas import ResolvedResearchArea
from app.research.semantic_limits import MAX_ELIGIBLE_EVENTS
from app.schemas.research_execution import (
    AggregateItem,
    ExecutionFilters,
    ExecutionGrouping,
    ExecutionMetric,
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


async def aggregate_selection(
    connection: AsyncConnection,
    settings: Settings,
    filters: ExecutionFilters,
    metric: ExecutionMetric,
    group_by: ExecutionGrouping,
    area: ResolvedResearchArea | None,
) -> list[AggregateItem]:
    # All matching occurrences, including effective venue overrides, not one date/event.
    sql = research_sql(occurrences=True)
    params = parameters(filters.model_copy(update={"entity_type": "event"}), settings, area)
    count = {
        "event_count": "entity_key",
        "occurrence_count": "date_key",
        "venue_count": "venue_id",
        "organization_count": "organization_id",
    }[metric]
    key, name, join = {
        "venue": ("venue_id::text", "venue_name", ""),
        "organization": ("organization_id::text", "organization_name", ""),
        "category": (
            "category->>'id'",
            "category->>'name'",
            "CROSS JOIN LATERAL jsonb_array_elements(categories) category",
        ),
    }[group_by]
    rows = (
        await connection.execute(
            text(f"""WITH selected AS ({sql})
        SELECT {key} key,{name} name,count(DISTINCT {count}) value
        FROM selected {join} WHERE {key} IS NOT NULL
        GROUP BY {key},{name}
        ORDER BY value DESC,lower({name}) COLLATE "C",({key}) COLLATE "C" LIMIT 20"""),
            params,
        )
    ).mappings()
    return [AggregateItem.model_validate(dict(r)) for r in rows]
