from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.admin_database import AdminConnectionDep
from app.auth.service import require_origin
from app.database import SettingsDep
from app.repositories.geo import import_area
from app.schemas.geo import GeoArea, GeoAreaImport, GeoAreaSearchFilters, GeoAreaSearchResponse
from app.services.geo.scopes import resolve_geo_scope
from app.services.nominatim import NominatimClient

router = APIRouter(prefix="/geo/areas", tags=["Geo areas"])


def get_provider(settings: SettingsDep) -> NominatimClient:
    return NominatimClient(settings)


ProviderDep = Annotated[NominatimClient, Depends(get_provider)]


@router.get("/search", response_model=GeoAreaSearchResponse)
async def search(
    provider: ProviderDep, filters: Annotated[GeoAreaSearchFilters, Query()]
) -> GeoAreaSearchResponse:
    return GeoAreaSearchResponse(items=await provider.search_areas(filters.q, filters.limit))


@router.post("", response_model=GeoArea)
async def create(
    request: Request,
    settings: SettingsDep,
    identity: GeoAreaImport,
    admin: AdminConnectionDep,
    provider: ProviderDep,
) -> GeoArea:
    require_origin(request, settings)
    return await import_area(admin, identity, provider)


@router.get("/{geo_scope_id}", response_model=GeoArea)
async def get(geo_scope_id: UUID, admin: AdminConnectionDep) -> GeoArea:
    return (await resolve_geo_scope(admin, geo_scope_id)).area
