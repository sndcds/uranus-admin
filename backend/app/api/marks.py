from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from app.admin_database import AdminConnectionDep
from app.auth.dependencies import AdminPrincipal, get_current_admin
from app.database import ConnectionDep
from app.schemas.marks import MarkCreate, MarkDetail, MarkFilters, MarkPage, MarkUpdate
from app.services.marks import create_mark, detail_in_transaction, mark_page, update_mark

router = APIRouter(tags=["Record marks"])
PrincipalDep = Annotated[AdminPrincipal, Depends(get_current_admin)]


@router.get("/record-marks", response_model=MarkPage)
async def list_marks(
    admin: AdminConnectionDep, filters: Annotated[MarkFilters, Query()]
) -> MarkPage:
    return await mark_page(admin, filters)


@router.post("/record-marks", response_model=MarkDetail, status_code=201)
async def add_mark(
    body: MarkCreate, admin: AdminConnectionDep, source: ConnectionDep, principal: PrincipalDep
) -> MarkDetail:
    return await create_mark(admin, source, body, principal.subject)


@router.get("/record-marks/{mark_id}", response_model=MarkDetail)
async def get_mark(mark_id: UUID, admin: AdminConnectionDep) -> MarkDetail:
    async with admin.begin():
        await admin.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        return await detail_in_transaction(admin, mark_id)


@router.patch("/record-marks/{mark_id}", response_model=MarkDetail)
async def change_mark(
    mark_id: UUID, body: MarkUpdate, admin: AdminConnectionDep, principal: PrincipalDep
) -> MarkDetail:
    return await update_mark(admin, mark_id, body, principal.subject)
