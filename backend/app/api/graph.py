from typing import Annotated

from fastapi import APIRouter, Query

from app.database import ConnectionDep, SettingsDep
from app.repositories.graph import explore, search
from app.schemas.graph import GraphFilters, GraphResponse, GraphSearchFilters, GraphSearchResponse

router = APIRouter(tags=["Relationship graph"])


@router.get("/graph/search", response_model=GraphSearchResponse)
async def graph_search(
    connection: ConnectionDep,
    filters: Annotated[GraphSearchFilters, Query()],
) -> GraphSearchResponse:
    return await search(connection, filters)


@router.get("/graph", response_model=GraphResponse)
async def graph(
    connection: ConnectionDep,
    settings: SettingsDep,
    filters: Annotated[GraphFilters, Query()],
) -> GraphResponse:
    return await explore(connection, settings, filters)
