from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.database import ConnectionDep, SettingsDep
from app.schemas.finding import FindingFilters, FindingPage
from app.services.quality.venues import get_findings

router = APIRouter(prefix="/quality", tags=["Quality"])


@router.get(
    "/venues/missing-geolocation",
    response_model=FindingPage,
    summary="Venues without a geolocation",
    description="Finds NULL/empty PostGIS points and counts upcoming dates by effective venue. "
    "Includes address, organization and publication relevance in the generic finding contract.",
)
async def missing_geolocation(
    connection: ConnectionDep,
    settings: SettingsDep,
    organization_id: UUID | None = None,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> FindingPage:
    filters = FindingFilters(organization_id=organization_id, page=page, page_size=page_size)
    return await get_findings(connection, settings, filters, datetime.now(UTC))
