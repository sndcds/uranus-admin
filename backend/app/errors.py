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
    return error_response(exc.status, exc.code, exc.message)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Do not echo arbitrary input, tokens or PII from validation errors.
    return error_response(422, "invalid_input", "Invalid query parameters or request body.")


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return error_response(exc.status_code, "http_error", "Request could not be processed.")
