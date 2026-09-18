from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.database import ConnectionDep, SettingsDep
from app.repositories.graph import explore, search
from app.schemas.graph import GraphFilters, GraphResponse, GraphSearchFilters, GraphSearchResponse
from app.services.geo.scopes import request_geo_scope

router = APIRouter(tags=["Relationship graph"])


@router.get("/graph/search", response_model=GraphSearchResponse)
async def graph_search(
    request: Request,
    connection: ConnectionDep,
    filters: Annotated[GraphSearchFilters, Query()],
) -> GraphSearchResponse:
    geo = await request_geo_scope(request, filters.geo_scope_id)
    return await search(connection, filters, geo.ewkb if geo else None)


@router.get("/graph", response_model=GraphResponse)
async def graph(
    connection: ConnectionDep,
    settings: SettingsDep,
    filters: Annotated[GraphFilters, Query()],
) -> GraphResponse:
    return await explore(connection, settings, filters)
