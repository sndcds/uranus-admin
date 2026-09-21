"""Cookie session + exact Origin; no bearer/dev credentials or URL parameters."""

import asyncio
from contextlib import suppress
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.auth.service import AdminPrincipal, session_identity
from app.errors import APIError, error_response
from app.sql_console.policy import ConsoleError
from app.sql_console.protocol import Ack, Cancel, client_message
from app.sql_console.runtime import ConsoleRuntime

router = APIRouter()


async def authorize(socket: WebSocket) -> AdminPrincipal:
    settings = socket.app.state.settings
    if not settings.auth_public_origin or socket.headers.getlist("origin") != [
        settings.auth_public_origin
    ]:
        raise APIError(403, "csrf_rejected", "Request origin could not be verified.")
    if socket.query_params or socket.headers.get("authorization"):
        raise APIError(403, "csrf_rejected", "Invalid console handshake.")
    cookie = socket.cookies.get(settings.session_cookie)
    if not cookie:
        raise APIError(401, "authentication_required", "Administrator session required.")
    principal = await session_identity(socket, settings, cookie)
    if not principal.system_admin:
        raise APIError(403, "admin_access_denied", "System administrator permission required.")
    if settings.sql_console_database_url is None:
        raise APIError(503, "database_unavailable", "SQL console unavailable.")
    return principal


@router.websocket("/api/v1/sql-console/ws")
async def console_socket(socket: WebSocket) -> None:
    try:
        await authorize(socket)
    except APIError as exc:
        if "websocket.http.response" in socket.scope.get("extensions", {}):
            await socket.send_denial_response(error_response(exc.status, exc.code, exc.message))
        else:
            await socket.close(code=1008)
        return
    await socket.accept()
    runtime: ConsoleRuntime = socket.app.state.sql_console
    active: asyncio.Task[None] | None = None
    request_id = ""
    expected_batch = 0
    ack: asyncio.Future[None] | None = None
    connected = True

    async def send(payload: dict[str, Any]) -> None:
        nonlocal ack, expected_batch
        if not connected:
            return
        if payload["type"] == "rows":
            expected_batch = payload["batch"]
            ack = asyncio.get_running_loop().create_future()
        await socket.send_json(payload)

    async def acknowledge(batch: int) -> None:
        if ack is None or batch != expected_batch:
            raise ConsoleError("protocol_error")
        await ack

    try:
        while True:
            async with asyncio.timeout(60):
                frame = await socket.receive()
            if frame["type"] == "websocket.disconnect":
                break
            raw = frame.get("text")
            if raw is None or len(raw.encode()) > 200_000:
                await socket.close(code=1009)
                break
            try:
                message = client_message.validate_json(raw)
            except ValidationError:
                await socket.close(code=1008)
                break
            if isinstance(message, Ack):
                if (
                    str(message.request_id) != request_id
                    or message.batch != expected_batch
                    or ack is None
                    or ack.done()
                ):
                    await socket.close(code=1008)
                    break
                ack.set_result(None)
            elif isinstance(message, Cancel):
                if active and not active.done() and str(message.request_id) == request_id:
                    active.cancel()
                    # Complete cancellation before accepting another execute/cancel.
                    await active
            else:
                if active and not active.done():
                    await send(
                        {
                            "v": 1,
                            "type": "error",
                            "request_id": str(message.request_id),
                            "code": "busy",
                        }
                    )
                    continue
                try:
                    # Revocation, grant removal and idle/absolute expiry apply to every query.
                    principal = await authorize(socket)
                    request_id = str(message.request_id)
                    active = runtime.start(message, principal.subject, send, acknowledge)
                    # Enter the supervised task before consuming an already queued cancel.
                    # Cancelling a never-started asyncio task cannot run its cleanup/final event.
                    await asyncio.sleep(0)
                except APIError as exc:
                    await socket.close(code=4401 if exc.status == 401 else 4403)
                    break
                except ConsoleError as exc:
                    await send(
                        {
                            "v": 1,
                            "type": "error",
                            "request_id": str(message.request_id),
                            "code": exc.code,
                        }
                    )
    except (WebSocketDisconnect, TimeoutError, RuntimeError):
        pass
    finally:
        connected = False
        if active and not active.done():
            active.cancel()
            with suppress(asyncio.CancelledError):
                await active
        with suppress(RuntimeError, OSError):
            await socket.close()
