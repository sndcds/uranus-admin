from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.admin_database import AdminConnectionDep
from app.auth.service import require_origin
from app.database import ConnectionDep, SettingsDep
from app.errors import APIError
from app.repositories import geocode
from app.schemas.geocode import (
    GeocodeFilters,
    GeocodePage,
    GeocodeRequestDetail,
    GeocodeRetryResponse,
)

router = APIRouter(prefix="/geocode/requests", tags=["Location suggestions"])


@router.get("", response_model=GeocodePage)
async def requests(
    request: Request,
    admin: AdminConnectionDep,
    source: ConnectionDep,
    filters: Annotated[GeocodeFilters, Query()],
) -> GeocodePage:
    if len(request.query_params.multi_items()) != len(request.query_params):
        raise APIError(422, "invalid_input", "Duplicate query parameters are not allowed.")
    return await geocode.page(admin, source, filters)


@router.get("/{key}", response_model=GeocodeRequestDetail)
async def request_detail(
    key: UUID, request: Request, admin: AdminConnectionDep, source: ConnectionDep
) -> GeocodeRequestDetail:
    if request.query_params:
        raise APIError(422, "invalid_input", "Query parameters are not allowed.")
    return await geocode.detail(admin, source, key)


@router.post("/{key}/retry", response_model=GeocodeRetryResponse, status_code=202)
async def retry(
    key: UUID,
    request: Request,
    settings: SettingsDep,
    admin: AdminConnectionDep,
    source: ConnectionDep,
) -> GeocodeRetryResponse:
    require_origin(request, settings)
    if request.query_params:
        raise APIError(422, "invalid_input", "Query parameters are not allowed.")
    async for chunk in request.stream():
        if chunk:
            raise APIError(422, "invalid_input", "Request body is not allowed.")
    await geocode.retry(admin, source, key)
    return GeocodeRetryResponse(id=key)
