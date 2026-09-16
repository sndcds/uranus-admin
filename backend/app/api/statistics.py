from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.database import ConnectionDep, SettingsDep
from app.schemas.statistics import EntityStatisticsResponse, StatisticsFilters
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
    connection: ConnectionDep,
    settings: SettingsDep,
    filters: Annotated[StatisticsFilters, Query()],
) -> EntityStatisticsResponse:
    return await get_statistics(connection, settings, filters, datetime.now(UTC))
