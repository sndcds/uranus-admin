import asyncio
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

from app.admin_database import create_admin_engine
from app.api import (
    activity,
    assignments,
    checks,
    dashboard,
    entities,
    findings,
    geo,
    geocode,
    graph,
    health,
    inbox,
    marks,
    notifications,
    quality,
    queues,
    sql_console,
    sql_diagnostics,
    sql_provenance,
    statistics,
    timeline,
)
from app.auth.body_limit import AuthBodyLimitMiddleware
from app.auth.dependencies import get_current_admin
from app.auth.routes import router as auth_router
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
from app.sql_console.runtime import ConsoleRuntime


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    debug_logging = settings.app_debug and (
        settings.app_env in {"development", "test"} or settings.allow_production_debug
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.password_slots = asyncio.Semaphore(4)
        configure_logging(settings.log_level, debug=debug_logging)
        engine = create_engine(settings)
        application.state.engine = engine
        admin_engine = create_admin_engine(settings)
        application.state.admin_engine = admin_engine
        application.state.sql_console = ConsoleRuntime(settings)
        try:
            yield
        finally:
            await application.state.sql_console.close()
            await engine.dispose()
            if admin_engine is not None:
                await admin_engine.dispose()

    application = FastAPI(
        title="Kulturbytes Admin API",
        version="0.1.0",
        lifespan=lifespan,
        description="Internal reporting API with independent system administrator authentication.",
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
            exc_info=(type(exc), exc, exc.__traceback__) if debug_logging else None,
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
    application.include_router(auth_router)
    # WebSocket uses cookie-only authorization, including exact Origin, in its handshake.
    application.include_router(sql_console.router)
    admin = APIRouter(
        prefix="/api/v1",
        dependencies=[Depends(get_current_admin)],
        responses={
            401: {"model": ErrorResponse},
            403: {"model": ErrorResponse},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    for router in (
        dashboard.router,
        inbox.router,
        assignments.router,
        findings.router,
        sql_diagnostics.router,
        sql_provenance.router,
        entities.router,
        quality.router,
        activity.router,
        graph.router,
        geo.router,
        statistics.router,
        timeline.router,
        queues.router,
        checks.router,
        marks.router,
        notifications.router,
        geocode.router,
    ):
        admin.include_router(router)
    application.include_router(admin)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "X-Admin-CSRF", "Content-Type"],
        allow_credentials=False,
    )
    application.add_middleware(AuthBodyLimitMiddleware)
    application.add_middleware(RequestLoggingMiddleware, debug=debug_logging)
    return application


app = create_app()
