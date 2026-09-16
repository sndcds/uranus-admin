from typing import Literal

from asyncpg.exceptions import PostgresError  # type: ignore[import-untyped]
from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.admin_database import connect_admin
from app.database import ConnectionDep, SettingsDep
from app.errors import APIError, ErrorResponse
from app.storage_preflight import RUNTIME_GRANTS, StorageIssue, check_grants, check_schema

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Process liveness",
    description="Confirms the HTTP process is running; does not access PostgreSQL.",
)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get(
    "/ready",
    response_model=HealthResponse,
    summary="Database readiness",
    description="Checks source and configured admin storage, migration compatibility "
    "and effective runtime grants.",
    responses={503: {"model": ErrorResponse}},
)
async def ready(
    request: Request, connection: ConnectionDep, settings: SettingsDep
) -> HealthResponse:
    await connection.execute(text("SELECT 1"))
    # Source-only development is explicit; staging/production always requires admin storage.
    if (
        settings.admin_database_url is None
        and settings.app_env in {"development", "test"}
        and settings.dev_auth_enabled
    ):
        return HealthResponse()
    try:
        async with connect_admin(request) as admin, admin.begin():
            await admin.execute(text("SET TRANSACTION READ ONLY"))
            await check_schema(admin)
            await check_grants(admin, RUNTIME_GRANTS)
    except (StorageIssue, SQLAlchemyError, PostgresError, OSError, TimeoutError):
        raise APIError(503, "admin_storage_unconfigured", "Admin storage is not ready.") from None
    return HealthResponse()
