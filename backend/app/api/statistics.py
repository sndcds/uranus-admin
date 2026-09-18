from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.database import ConnectionDep, SettingsDep
from app.schemas.event_content import EventContentFilters, EventContentStatistics
from app.schemas.statistics import EntityStatisticsResponse, StatisticsFilters
from app.services.event_content import get_event_content
from app.services.geo.scopes import request_geo_scope
from app.services.statistics import get_statistics

router = APIRouter(prefix="/statistics", tags=["Statistics"])


@router.get(
    "/entities",
    response_model=EntityStatisticsResponse,
    summary="Entity creation time series",
    description="Seven creation metrics in an exact half-open range. Teameinladungen uses "
    "invited_at; other types use created_at. Natural local bucket boundaries, zero-filled "
    "counts, at most 500 buckets and 365 days. Optional previous-range totals and seven "
    "recent entities share the same read-only snapshot. No inferred authors or history.",
)
async def entities(
    request: Request,
    connection: ConnectionDep,
    settings: SettingsDep,
    filters: Annotated[StatisticsFilters, Query()],
) -> EntityStatisticsResponse:
    geo = await request_geo_scope(request, filters.geo_scope_id)
    return await get_statistics(
        connection, settings, filters, datetime.now(UTC), geo.ewkb if geo else None
    )


@router.get(
    "/events/content",
    response_model=EventContentStatistics,
    summary="Event content by creation time",
)
async def event_content(
    request: Request,
    connection: ConnectionDep,
    settings: SettingsDep,
    filters: Annotated[EventContentFilters, Query()],
) -> EventContentStatistics:
    geo = await request_geo_scope(request, filters.geo_scope_id)
    return await get_event_content(
        connection, settings, filters, datetime.now(UTC), geo.ewkb if geo else None
    )
