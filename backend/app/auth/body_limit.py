"""Bound login, area-identity and planning JSON, even without Content-Length."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import error_response


class AuthBodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limits = {
            "/auth/login": 8192,
            "/api/v1/geo/areas": 8192,
            "/api/v1/research/plan": 32 * 1024,
        }
        limit = limits.get(scope.get("path", ""))
        if scope["type"] != "http" or limit is None:
            await self.app(scope, receive, send)
            return
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > limit:
                await error_response(413, "request_too_large", "Request is too large.")(
                    scope, receive, send
                )
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive() -> Message:
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, bounded_receive, send)
