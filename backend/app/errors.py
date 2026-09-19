import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
        headers={"WWW-Authenticate": "Bearer"} if status == 401 else None,
    )


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    if 500 <= exc.status < 600:
        settings = request.app.state.settings
        debug = settings.app_debug and (
            settings.app_env in {"development", "test"} or settings.allow_production_debug
        )
        logging.getLogger("admin.error").error(
            exc.code,
            extra={
                "error_type": type(exc).__name__,
                "status_code": exc.status,
                "method": request.method,
                "route": getattr(request.scope.get("route"), "path", "unmatched"),
            },
            exc_info=(type(exc), exc, exc.__traceback__) if debug else None,
        )
    return error_response(exc.status, exc.code, exc.message)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Do not echo arbitrary input, tokens or PII from validation errors.
    return error_response(422, "invalid_input", "Invalid query parameters or request body.")


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return error_response(exc.status_code, "http_error", "Request could not be processed.")
