from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.database import ConnectionDep
from app.errors import ErrorResponse

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
    description="Checks the database connection; does not certify auth or schema compatibility.",
    responses={503: {"model": ErrorResponse}},
)
async def ready(connection: ConnectionDep) -> HealthResponse:
    await connection.execute(text("SELECT 1"))
    return HealthResponse()
