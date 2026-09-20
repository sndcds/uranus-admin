from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import Settings
from app.errors import APIError
from app.repositories.quality_sources import load_sources
from app.repositories.venues import QUALITY_SQL, RULE, query_parameters
from app.schemas.finding import Finding, FindingFilters, FindingPage, Pagination
from app.services.geo.membership import filter_live_findings
from app.services.quality.core import CORE_RULES, QualityContext, RuleResult, evaluate_core
from app.services.quality.venues import map_venue
from app.services.queues import queue_findings


async def scan(connection: AsyncConnection, settings: Settings, now: datetime) -> list[RuleResult]:
    if settings.uranus_timestamp_timezone is None:
        raise APIError(503, "source_timezone_unconfigured", "Source timezone must be configured.")
    sources = await load_sources(connection)
    rows = (await connection.execute(text(QUALITY_SQL), query_parameters(settings, now))).mappings()
    results = [
        RuleResult(
            RULE,
            [map_venue(dict(row), now) for row in rows],
            {("venue", str(row["uuid"])) for row in sources.rows["venue"]},
        )
    ]
    context = QualityContext(sources, settings, now)
    for rule in CORE_RULES:
        results.append(evaluate_core(rule, sources, settings, now, context))
    results.extend(await queue_findings(connection, settings, now))
    return results


def findings_page(items: list[Finding], filters: FindingFilters, now: datetime) -> FindingPage:
    items = [
        item
        for item in items
        if (filters.severity is None or item.severity == filters.severity)
        and (filters.entity_type is None or item.entity_type == filters.entity_type)
        and (filters.entity_key is None or item.entity_key == filters.entity_key)
        and (filters.rule is None or item.rule == filters.rule)
        and (filters.organization_id is None or item.organization_id == filters.organization_id)
        and (filters.status is None or item.status == filters.status)
        and (not filters.active_only or item.status != "resolved")
    ]
    items.sort(key=lambda item: (-item.priority_score, item.id))
    total = len(items)
    start = (filters.page - 1) * filters.page_size
    return FindingPage(
        items=items[start : start + filters.page_size],
        observed_at=now,
        pagination=Pagination(
            page=filters.page,
            page_size=filters.page_size,
            total=total,
            pages=(total + filters.page_size - 1) // filters.page_size,
        ),
    )


async def get_findings(
    connection: AsyncConnection,
    settings: Settings,
    filters: FindingFilters,
    now: datetime,
    geo_scope_wkb: bytes | None = None,
) -> FindingPage:
    results = await scan(connection, settings, now)
    items = await filter_live_findings(
        connection, [item for result in results for item in result.findings], geo_scope_wkb
    )
    return findings_page(items, filters, now)
