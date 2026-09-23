from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from app.admin_database import AdminConnectionDep
from app.auth.dependencies import AdminPrincipal, get_current_admin
from app.database import SettingsDep
from app.schemas.assignments import (
    AdminOptionPage,
    Assignment,
    AssignmentCreate,
    AssignmentLookup,
    AssignmentUpdate,
)
from app.services.assignments import (
    active_assignment,
    admin_options,
    assignment_detail,
    create_assignment,
    update_assignment,
)

router = APIRouter(tags=["Assignments"])
PrincipalDep = Annotated[AdminPrincipal, Depends(get_current_admin)]


@router.get("/admins", response_model=AdminOptionPage)
async def admins(admin: AdminConnectionDep, settings: SettingsDep) -> AdminOptionPage:
    return AdminOptionPage(items=await admin_options(admin), admin_timezone=settings.admin_timezone)


@router.get("/assignments", response_model=Assignment | None)
async def assignment_for_task(
    admin: AdminConnectionDep,
    lookup: Annotated[AssignmentLookup, Query()],
) -> Assignment | None:
    return await active_assignment(admin, lookup)


@router.post("/assignments", response_model=Assignment, status_code=201)
async def add_assignment(
    body: AssignmentCreate, admin: AdminConnectionDep, principal: PrincipalDep
) -> Assignment:
    return await create_assignment(admin, body, principal.subject)


@router.get("/assignments/{assignment_id}", response_model=Assignment)
async def get_assignment(assignment_id: UUID, admin: AdminConnectionDep) -> Assignment:
    async with admin.begin():
        await admin.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        return await assignment_detail(admin, assignment_id)


@router.patch("/assignments/{assignment_id}", response_model=Assignment)
async def change_assignment(
    assignment_id: UUID,
    body: AssignmentUpdate,
    admin: AdminConnectionDep,
    principal: PrincipalDep,
) -> Assignment:
    return await update_assignment(admin, assignment_id, body, principal.subject)
