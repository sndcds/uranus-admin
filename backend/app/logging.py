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
        for key in (
            "request_id",
            "query_hash",
            "candidate_count",
            "entities_scanned",
            "requests_synchronized",
            "requests_created",
            "requests_checked",
            "candidates_found",
            "ambiguous",
            "not_found",
            "failed",
            "stale",
            "insufficient_input",
            "method",
            "route",
            "status_code",
            "duration_ms",
            "error_type",
            "rule",
            "recipe_id",
            "view_id",
            "source_id",
            "datasource",
            "finding_id_hash",
            "row_count",
            "organization_id",
            "delivery_id",
            "retry_of_delivery_id",
            "actor_subject",
            "candidates_detected",
            "deliveries_queued",
            "deliveries_sent",
            "deliveries_failed",
            "deliveries_suppressed",
        ):
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
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


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
                headers = list(message.get("headers", []))
                headers = [
                    (key, value)
                    for key, value in headers
                    if key.lower() not in {b"cache-control", b"vary"}
                ]
                headers.extend(
                    [
                        (b"cache-control", b"private, no-store"),
                        (b"vary", b"Authorization, Cookie, Origin"),
                    ]
                )
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, capture)
        except Exception as exc:
            # Keep errors in our logger, with details only for explicitly enabled debugging.
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
