from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.admin_database import connect_admin
from app.database import ConnectionDep, SettingsDep
from app.schemas.finding import FindingFilters, FindingPage
from app.services.checks import persisted_page
from app.services.quality.engine import get_findings

router = APIRouter(tags=["Findings"])


@router.get(
    "/findings",
    response_model=FindingPage,
    summary="List live quality findings",
    description="Paginated current findings. Only open findings exist in live mode; "
    "other status filters return an empty live result, not historical workflow data. "
    "Ordered by priority_score descending and stable finding ID.",
)
async def findings(
    request: Request,
    connection: ConnectionDep,
    settings: SettingsDep,
    filters: Annotated[FindingFilters, Query()],
) -> FindingPage:
    if filters.mode == "persisted":
        async with connect_admin(request) as admin:
            return await persisted_page(admin, filters, datetime.now(UTC))
    return await get_findings(connection, settings, filters, datetime.now(UTC))
