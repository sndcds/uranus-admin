from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.database import ConnectionDep, SettingsDep
from app.repositories.activity import activity_page
from app.schemas.activity import ActivityFilters, ActivityPage

router = APIRouter(tags=["Activity"])


@router.get(
    "/dashboard/activity",
    response_model=ActivityPage,
    summary="List source record creations",
    description="Created timestamps only; no inferred login, join or decision history. "
    "Known timestamps descend with entity type/key ties. Unknown timestamps are a separate list.",
)
async def activity(
    connection: ConnectionDep, settings: SettingsDep, filters: Annotated[ActivityFilters, Query()]
) -> ActivityPage:
    return await activity_page(connection, settings, filters, datetime.now(UTC))
