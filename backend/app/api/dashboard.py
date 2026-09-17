from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Request

from app.admin_database import connect_admin
from app.database import ConnectionDep, SettingsDep
from app.schemas.dashboard import DashboardSummary, Period
from app.services.dashboard import get_summary

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "/summary",
    response_model=DashboardSummary,
    summary="Dashboard summary",
    description="Source-table creations in [from_at, to_at), plus stored unresolved findings. "
    "Only explicit mode=live runs a diagnostic scan. "
    "Today starts at midnight in ADMIN_TIMEZONE. "
    "Persisted mode includes latest and last successful check runs, independent of period.",
)
async def summary(
    request: Request,
    connection: ConnectionDep,
    settings: SettingsDep,
    period: Period = "24h",
    mode: Literal["persisted", "live"] = "persisted",
) -> DashboardSummary:
    if mode == "persisted":
        async with connect_admin(request) as admin:
            return await get_summary(connection, settings, period, datetime.now(UTC), admin)
    return await get_summary(connection, settings, period, datetime.now(UTC))
