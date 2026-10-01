"""Closed exact metrics over the shared public PostgreSQL Research population."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.errors import APIError
from app.repositories.research import eligible_event_ctes, parameters
from app.repositories.research_areas import ResolvedResearchArea
from app.research.semantic_documents import public_clean
from app.schemas.research_domain import DataPlan
from app.schemas.research_execution import ExecutionFilters
from app.schemas.research_unified import MetricRecord

MAX_TEXT_EVENTS = 10000
MAX_TEXT_CODEPOINTS = 2_000_000


async def rank_metric(
    connection: AsyncConnection,
    settings: Settings,
    plan: DataPlan,
    filters: ExecutionFilters,
    area: ResolvedResearchArea | None,
) -> list[MetricRecord]:
    params = parameters(filters, settings, area)
    if plan.metric == "description_characters":
        # Probe size in SQL before transferring prose. No partial ranking on overflow.
        ctes = eligible_event_ctes()
        size = (
            (
                await connection.execute(
                    text(f"""{ctes}, descriptions AS (
            SELECT DISTINCT entity_key,description FROM matched_events
        ) SELECT count(*) count,COALESCE(sum(char_length(description)),0) characters
          FROM descriptions"""),
                    params,
                )
            )
            .mappings()
            .one()
        )
        if size["count"] > MAX_TEXT_EVENTS or size["characters"] > MAX_TEXT_CODEPOINTS:
            raise APIError(422, "research_execution_too_broad", "Narrow the research request.")
        rows = (
            await connection.execute(
                text(f"""{ctes}
            SELECT DISTINCT entity_key,name,description FROM matched_events
            ORDER BY entity_key"""),
                params,
            )
        ).mappings()
        records = [
            MetricRecord(
                key=str(r["entity_key"]), name=r["name"], value=len(public_clean(r["description"]))
            )
            for r in rows
        ]
        return sorted(
            records, key=lambda r: ((-r.value if plan.ordering == "desc" else r.value), r.key)
        )[: plan.limit]
    key, label, expression, join = {
        ("event", "occurrence_count"): ("entity_key::text", "name", "date_key", ""),
        ("organization", "event_count"): (
            "organization_id::text",
            "organization_name",
            "entity_key",
            "",
        ),
        ("organization", "venue_count"): (
            "organization_id::text",
            "organization_name",
            "venue_id",
            "",
        ),
        ("venue", "occurrence_count"): ("venue_id::text", "venue_name", "date_key", ""),
        ("category", "event_count"): (
            "category->>'id'",
            "category->>'name'",
            "entity_key",
            "CROSS JOIN LATERAL jsonb_array_elements(categories) category",
        ),
    }[(plan.entity_type, plan.metric)]
    direction = {"asc": "ASC", "desc": "DESC"}[plan.ordering]
    rows = (
        await connection.execute(
            text(f"""{eligible_event_ctes()}
        SELECT {key} key,{label} name,count(DISTINCT {expression}) value
        FROM matched_events {join} WHERE {key} IS NOT NULL
        GROUP BY {key},{label} ORDER BY value {direction},({key}) COLLATE "C"
        LIMIT :rank_limit"""),
            {**params, "rank_limit": plan.limit},
        )
    ).mappings()
    return [MetricRecord.model_validate(dict(r)) for r in rows]
