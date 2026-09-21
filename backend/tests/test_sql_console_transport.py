"""Real Uvicorn HTTP upgrade denial, including the reported disabled-console case."""

import asyncio
import logging
import socket
from unittest.mock import AsyncMock, patch

import pytest
import uvicorn
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from app.__main__ import main
from app.auth.service import AdminPrincipal
from app.config import Settings
from app.main import create_app


@pytest.mark.parametrize(
    ("origin", "cookie", "status"),
    [
        ("http://fixture.example", True, 503),
        ("http://wrong.example", True, 403),
        ("http://fixture.example", False, 401),
    ],
)
async def test_real_handshake_denial_completes_without_asgi_error(caplog, origin, cookie, status):
    settings = Settings(_env_file=None, app_env="test", auth_public_origin="http://fixture.example")
    with patch("app.__main__.Settings", return_value=settings), patch("uvicorn.run") as run:
        main()
    options = run.call_args.kwargs
    assert options["workers"] == 1
    assert options["ws_max_size"] == 200_000
    assert options["ws"] == "wsproto"
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            ws=options["ws"],
            lifespan="off",
            log_config=None,
            access_log=False,
        )
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    task = None
    with (
        caplog.at_level(logging.ERROR, logger="uvicorn.error"),
        patch(
            "app.api.sql_console.session_identity",
            AsyncMock(return_value=AdminPrincipal(subject="admin:fixture", system_admin=True)),
        ),
        patch("app.sql_console.runtime.asyncpg.connect") as database,
    ):
        try:
            task = asyncio.create_task(server.serve(sockets=[sock]))
            async with asyncio.timeout(3):
                while not server.started:  # noqa: ASYNC110 - bounded server readiness
                    await asyncio.sleep(0.01)
            headers = {"Cookie": "admin_session=" + "a" * 43} if cookie else {}
            with pytest.raises(InvalidStatus) as rejection:
                async with connect(
                    f"ws://127.0.0.1:{sock.getsockname()[1]}/api/v1/sql-console/ws",
                    origin=origin,
                    additional_headers=headers,
                ):
                    pytest.fail("A disabled or unauthorized console must never accept the socket")
            assert rejection.value.response.status_code == status
            assert b'"error"' in rejection.value.response.body
            database.assert_not_called()
        finally:
            server.should_exit = True
            if task:
                async with asyncio.timeout(3):
                    await task
            sock.close()
    assert not any("ASGI callable" in record.getMessage() for record in caplog.records)


async def test_real_transport_streams_and_bounds_fragmented_utf8_frames():
    import json
    from uuid import uuid4

    from websockets.exceptions import ConnectionClosed

    from app.sql_console.runtime import ConsoleRuntime
    from tests.test_sql_console import FakeConnection, configured

    settings = configured()
    app = create_app(settings)
    runtime = ConsoleRuntime(settings)
    app.state.sql_console = runtime
    connection = FakeConnection(count=1)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            ws="wsproto",
            ws_max_size=200_000,
            lifespan="off",
            log_config=None,
            access_log=False,
        )
    )
    task = None
    with (
        patch(
            "app.api.sql_console.session_identity",
            AsyncMock(return_value=AdminPrincipal(subject="admin:fixture", system_admin=True)),
        ),
        patch("app.sql_console.runtime.asyncpg.connect", AsyncMock(return_value=connection)),
        patch("app.sql_console.runtime.assert_identity", AsyncMock()),
    ):
        try:
            task = asyncio.create_task(server.serve(sockets=[sock]))
            async with asyncio.timeout(3):
                while not server.started:  # noqa: ASYNC110 - bounded server readiness
                    await asyncio.sleep(0.01)
            async with connect(
                f"ws://127.0.0.1:{sock.getsockname()[1]}/api/v1/sql-console/ws",
                origin="http://testserver",
                additional_headers={"Cookie": "admin_session=" + "a" * 43},
            ) as client:
                base = {"v": 1, "request_id": str(uuid4())}
                await client.send(json.dumps({**base, "type": "execute", "sql": "SELECT 1"}))
                types = []
                async with asyncio.timeout(3):
                    while True:
                        message = json.loads(await client.recv())
                        types.append(message["type"])
                        if message["type"] == "rows":
                            assert message["rows"] == [{"value": 1}]
                            await client.send(
                                json.dumps({**base, "type": "ack", "batch": message["batch"]})
                            )
                        if message["type"] == "complete":
                            break
                assert types == ["started", "columns", "rows", "complete"]
                connection.transaction_object.rollback.assert_awaited_once()
                connection.close.assert_awaited_once()
                with pytest.raises(ConnectionClosed) as rejection:
                    # Both fragments individually fit; the UTF-8 message exceeds 200000 bytes.
                    await client.send(["ä" * 50000, "ä" * 50001])
                    await client.recv()
                assert rejection.value.rcvd.code == 1009
        finally:
            await runtime.close()
            server.should_exit = True
            if task:
                async with asyncio.timeout(3):
                    await task
            sock.close()
