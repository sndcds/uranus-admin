from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.admin_database import AdminConnectionDep
from app.auth.dependencies import AdminPrincipal, get_current_admin
from app.database import ConnectionDep, SettingsDep
from app.schemas.assignments import InboxFilters, InboxPage
from app.services.inbox import inbox_page

router = APIRouter(tags=["Admin inbox"])


@router.get("/inbox", response_model=InboxPage)
async def inbox(
    admin: AdminConnectionDep,
    source: ConnectionDep,
    settings: SettingsDep,
    filters: Annotated[InboxFilters, Query()],
    principal: Annotated[AdminPrincipal, Depends(get_current_admin)],
) -> InboxPage:
    return await inbox_page(
        admin,
        source,
        filters,
        datetime.now(UTC),
        settings.admin_timezone,
        principal.subject,
    )
