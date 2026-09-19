from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Request

from app.admin_database import connect_admin
from app.database import ConnectionDep, SettingsDep
from app.schemas.dashboard import DashboardSummary, Period
from app.services.dashboard import get_summary
from app.services.geo.scopes import request_geo_scope

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
    geo_scope_id: UUID | None = None,
) -> DashboardSummary:
    geo = await request_geo_scope(request, geo_scope_id)
    if mode == "persisted":
        async with connect_admin(request) as admin:
            return await get_summary(connection, settings, period, datetime.now(UTC), admin, geo)
    return await get_summary(connection, settings, period, datetime.now(UTC), geo=geo)
