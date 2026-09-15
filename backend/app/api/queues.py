from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.database import ConnectionDep, SettingsDep
from app.schemas.queues import QueueFilters, QueueKind, QueuePage
from app.services.queues import get_queue

router = APIRouter(tags=["Work queues"])


@router.get(
    "/work-queues/{kind}",
    response_model=QueuePage,
    summary="List operational work items",
    description="Partner requests, open invitations or inactive accounts. "
    "Age uses creation or actual invitation timestamp, never last login or joined time.",
)
async def queue(
    kind: QueueKind,
    connection: ConnectionDep,
    settings: SettingsDep,
    filters: Annotated[QueueFilters, Query()],
) -> QueuePage:
    return await get_queue(connection, settings, kind, filters, datetime.now(UTC))
