from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.database import ConnectionDep, SettingsDep
from app.schemas.finding import FindingFilters, FindingPage
from app.services.quality.venues import get_findings

router = APIRouter(tags=["Findings"])


@router.get(
    "/findings",
    response_model=FindingPage,
    summary="List live quality findings",
    description="Paginated current findings. Only open findings exist in live mode; "
    "other status filters return an empty live result, not historical workflow data. "
    "Ordered by severity, priority, publication relevance, observation time and stable ID.",
)
async def findings(
    connection: ConnectionDep,
    settings: SettingsDep,
    filters: Annotated[FindingFilters, Query()],
) -> FindingPage:
    return await get_findings(connection, settings, filters, datetime.now(UTC))
