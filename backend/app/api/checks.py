from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.admin_database import AdminConnectionDep
from app.admin_tables import check_run
from app.auth.dependencies import AdminPrincipal, get_current_admin
from app.database import ConnectionDep, SettingsDep
from app.errors import ErrorResponse
from app.schemas.checks import CheckRun, CheckRunPage, ReviewUpdate
from app.schemas.finding import Finding, Pagination
from app.services.checks import review, run_check

router = APIRouter(
    tags=["Check runs and review"],
    responses={409: {"model": ErrorResponse, "description": "Concurrent check or review"}},
)


@router.post(
    "/check-runs",
    response_model=CheckRun,
    summary="Run and persist all quality checks",
    description="Reads a source snapshot; writes admin history only. "
    "Failed scans never resolve findings.",
)
async def start_check(
    connection: ConnectionDep, admin: AdminConnectionDep, settings: SettingsDep
) -> CheckRun:
    return await run_check(connection, admin, settings)


@router.get(
    "/check-runs",
    response_model=CheckRunPage,
    summary="List persisted check runs",
    description="Newest start first, stable UUID ties. "
    "A running or failed run is not evidence of clean data.",
)
async def runs(
    admin: AdminConnectionDep,
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> CheckRunPage:
    async with admin.begin():
        total = int((await admin.execute(select(func.count()).select_from(check_run))).scalar_one())
        rows = (
            await admin.execute(
                select(check_run)
                .order_by(check_run.c.started_at.desc(), check_run.c.id)
                .limit(page_size)
                .offset((page - 1) * page_size)
            )
        ).mappings()
        return CheckRunPage(
            items=[CheckRun.model_validate(dict(row)) for row in rows],
            pagination=Pagination(
                page=page,
                page_size=page_size,
                total=total,
                pages=(total + page_size - 1) // page_size,
            ),
        )


@router.patch(
    "/finding-reviews",
    response_model=Finding,
    summary="Update a human finding review",
    description="Changes admin workflow only. "
    "Resolution is reserved for a successful covering recheck.",
)
async def update_review(
    body: ReviewUpdate,
    admin: AdminConnectionDep,
    connection: ConnectionDep,
    principal: Annotated[AdminPrincipal, Depends(get_current_admin)],
) -> Finding:
    return await review(admin, connection, body, principal.subject, datetime.now(UTC))
