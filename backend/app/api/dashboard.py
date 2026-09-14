from datetime import UTC, datetime

from fastapi import APIRouter

from app.database import ConnectionDep, SettingsDep
from app.schemas.dashboard import DashboardSummary, Period
from app.services.dashboard import get_summary

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Dashboard summary",
    description="Source-table creations in [from_at, to_at), plus live venue findings. "
    "Today starts at midnight in ADMIN_TIMEZONE. Historical check status is unavailable.",
)
async def summary(
    connection: ConnectionDep, settings: SettingsDep, period: Period = "24h"
) -> DashboardSummary:
    return await get_summary(connection, settings, period, datetime.now(UTC))
