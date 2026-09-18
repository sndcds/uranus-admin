from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.database import ConnectionDep, SettingsDep
from app.errors import APIError
from app.repositories.activity import activity_page
from app.schemas.activity import ActivityFilters, ActivityPage
from app.services.geo.scopes import request_geo_scope

router = APIRouter(tags=["Activity"])


@router.get(
    "/dashboard/activity",
    response_model=ActivityPage,
    summary="List source record creations",
    description="Created timestamps only; no inferred login, join or decision history. "
    "Known timestamps descend with entity type/key ties. Unknown timestamps are a separate list.",
)
async def activity(
    request: Request,
    connection: ConnectionDep,
    settings: SettingsDep,
    filters: Annotated[ActivityFilters, Query()],
) -> ActivityPage:
    if filters.cursor is not None and "page" in request.query_params:
        raise APIError(422, "invalid_input", "Choose page or cursor pagination.")
    geo = await request_geo_scope(request, filters.geo_scope_id)
    return await activity_page(
        connection, settings, filters, datetime.now(UTC), geo.ewkb if geo else None
    )
