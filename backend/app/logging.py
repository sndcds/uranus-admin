import json
import logging
from datetime import UTC, datetime
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import error_response


class JsonFormatter(logging.Formatter):
    def __init__(self, *, debug: bool = False) -> None:
        super().__init__()
        self.debug = debug

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for key in ("method", "route", "status_code", "duration_ms", "error_type", "rule"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if self.debug and record.exc_info:
            payload["traceback"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str, *, debug: bool = False) -> None:
    logger = logging.getLogger("admin")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(debug=debug))
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
    # SQL/parameters and Uvicorn's raw URL/query-string access logs may contain PII.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").disabled = True


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp, *, debug: bool = False) -> None:
        self.app = app
        self.debug = debug

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started, status = perf_counter(), 500
        response_started = False

        async def capture(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status = message["status"]
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, capture)
        except Exception as exc:
            # Keep errors in our logger, with details only for explicit local debugging.
            # Current routes are buffered JSON.
            logging.getLogger("admin.error").error(
                "internal_error",
                extra={"error_type": type(exc).__name__},
                exc_info=(type(exc), exc, exc.__traceback__) if self.debug else None,
            )
            if not response_started:
                await error_response(500, "internal_error", "Internal server error.")(
                    scope, receive, capture
                )
        finally:
            route = scope.get("route")
            logging.getLogger("admin.http").info(
                "http_request",
                extra={
                    "method": scope["method"],
                    "route": getattr(route, "path", "unmatched"),
                    "status_code": status,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                },
            )
