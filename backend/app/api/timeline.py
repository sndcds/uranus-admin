from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.admin_database import AdminConnectionDep
from app.database import ConnectionDep, SettingsDep
from app.repositories.timeline import timeline_page
from app.schemas.timeline import TimelineEntityType, TimelineFilters, TimelinePage

router = APIRouter(prefix="/entities", tags=["Entity timeline"])


@router.get(
    "/{entity_type}/{entity_key}/timeline",
    response_model=TimelinePage,
    summary="Read an entity's verified chronological history",
    description="Aggregates bounded source and admin workflow events. Every item has an "
    "evidenced timestamp; no missing time is synthesized.",
)
async def timeline(
    entity_type: TimelineEntityType,
    entity_key: UUID,
    filters: Annotated[TimelineFilters, Query()],
    source: ConnectionDep,
    admin: AdminConnectionDep,
    settings: SettingsDep,
) -> TimelinePage:
    return await timeline_page(
        source, admin, settings, entity_type, entity_key, filters, datetime.now(UTC)
    )
