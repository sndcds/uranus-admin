from contextlib import aclosing
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.admin_database import connect_admin
from app.database import SettingsDep, get_connection
from app.schemas.finding import FindingFilters, FindingPage
from app.services.checks import persisted_page
from app.services.quality.engine import get_findings

router = APIRouter(tags=["Findings"])


@router.get(
    "/findings",
    response_model=FindingPage,
    summary="List persisted or explicit live quality findings",
    description="Defaults to persisted findings without a source scan. Explicit mode=live runs "
    "a full diagnostic scan. Only open findings exist in live mode; "
    "other status filters return an empty live result, not historical workflow data. "
    "Ordered by priority_score descending and stable finding ID.",
)
async def findings(
    request: Request,
    settings: SettingsDep,
    filters: Annotated[FindingFilters, Query()],
) -> FindingPage:
    if filters.mode == "persisted":
        async with connect_admin(request) as admin:
            return await persisted_page(admin, filters, datetime.now(UTC))
    async with aclosing(get_connection(request)) as connections:
        connection = await anext(connections)
        return await get_findings(connection, settings, filters, datetime.now(UTC))
