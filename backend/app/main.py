import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from asyncpg.exceptions import PostgresError  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException

from app.api import dashboard, findings, health, quality
from app.auth.dependencies import get_current_admin
from app.config import Settings
from app.database import create_engine
from app.errors import (
    APIError,
    ErrorResponse,
    api_error_handler,
    error_response,
    http_error_handler,
    validation_error_handler,
)
from app.logging import RequestLoggingMiddleware, configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level)
        engine = create_engine(settings)
        application.state.engine = engine
        try:
            yield
        finally:
            await engine.dispose()

    application = FastAPI(
        title="Kulturbytes Admin API",
        version="0.1.0",
        lifespan=lifespan,
        description="Internal reporting API. Production auth is unavailable in milestone 1.",
        debug=False,  # Never return a traceback, including when APP_DEBUG is enabled.
        docs_url="/docs" if settings.openapi_enabled else None,
        openapi_url="/openapi.json" if settings.openapi_enabled else None,
        redoc_url=None,
    )
    application.state.settings = settings
    application.add_exception_handler(APIError, api_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(HTTPException, http_error_handler)  # type: ignore[arg-type]

    @application.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        unavailable = isinstance(exc, (SQLAlchemyError, PostgresError, OSError, TimeoutError))
        logging.getLogger("admin.error").error(
            "database_unavailable" if unavailable else "internal_error",
            extra={"error_type": type(exc).__name__},
        )
        return error_response(
            503 if unavailable else 500,
            "database_unavailable" if unavailable else "internal_error",
            "Database unavailable." if unavailable else "Internal server error.",
        )

    # Register expected infrastructure failures inside ExceptionMiddleware so the
    # access log and CORS middleware also see the actual 503 response.
    for exception_type in (SQLAlchemyError, PostgresError, OSError, TimeoutError):
        application.add_exception_handler(exception_type, internal_error)

    application.include_router(health.router)
    admin = APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(get_current_admin)],
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    for router in (dashboard.router, findings.router, quality.router):
        admin.include_router(router)
    application.include_router(admin)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_methods=["GET"],
        allow_headers=["Authorization"],
        allow_credentials=False,
    )
    application.add_middleware(RequestLoggingMiddleware)
    return application


app = create_app()
