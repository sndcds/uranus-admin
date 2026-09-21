"""Runtime against the actual reviewed DB provisioner, in its isolated *_test DB.

The existing Ansible fixture guards local host, DB name and pre-existing roles;
creates its own database from template0; and removes only its fixture objects.
"""

import asyncio
import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import asyncpg
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.sql_console.protocol import Execute
from app.sql_console.runtime import ConsoleRuntime, assert_identity

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def provisioned_console():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        if os.environ.get("CI"):
            pytest.fail("CI requires TEST_DATABASE_URL")
        pytest.skip("Set TEST_DATABASE_URL to a local disposable *_test database")
    path = Path(__file__).resolve().parents[2] / "ansible/tests"
    sys.path.insert(0, str(path))
    try:
        spec = importlib.util.spec_from_file_location(
            "console_provision_fixture", path / "test_sql_console.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.TEST_URL = url.replace("postgresql+asyncpg://", "postgresql://")
        cls = module.ConsoleDatabaseTests
        cls.setUpClass()
        fixture = cls()
        fixture.setUp()
        try:
            fixture.provision()
            fixture.conn.commit()
            args = fixture.connection_args
            # The fixture supplies only synthetic credentials, never an application DSN.
            reader = f"postgresql://uranus_console_reader:{module.PASSWORD}@{args['host']}:{args['port']}/{args['dbname']}"
            observer = {key: args[key] for key in ("host", "port", "user", "password")}
            observer["database"] = args["dbname"]
            observer["port"] = int(observer["port"])
            yield reader, observer
        finally:
            fixture.tearDown()
            cls.tearDownClass()
    finally:
        sys.path.remove(str(path))


def request(sql, limit=50):
    return Execute(v=1, type="execute", request_id=uuid4(), sql=sql, row_limit=limit)


def runtime_for(url):
    return ConsoleRuntime(
        Settings(_env_file=None, app_env="test", sql_console_database_url=SecretStr(url))
    )


async def collect(runtime, sql, limit=50):
    messages = []

    async def send(message):
        messages.append(message)

    await runtime.execute(request(sql, limit), "admin:fixture", send, AsyncMock())
    return messages


async def test_real_identity_and_db_enforced_boundary(provisioned_console):
    url, _ = provisioned_console
    conn = await asyncpg.connect(url)
    try:
        await assert_identity(conn)
        assert await conn.fetchval("SELECT current_user") == "uranus_console_reader"
        assert (
            await conn.fetchval("SELECT current_setting('search_path')")
            == "pg_catalog, uranus_console"
        )
        assert not await conn.fetchval(
            "SELECT has_database_privilege(current_user,current_database(),'TEMP')"
        )
        assert not await conn.fetchval(
            "SELECT has_database_privilege(current_user,current_database(),'CREATE')"
        )
        # Bypass the application AST deliberately: PostgreSQL must still deny these.
        for sql in [
            'SELECT * FROM uranus."user"',
            "SELECT * FROM admin.auth_account",
            "SELECT pg_sleep(1)",
            "SELECT pg_read_file('/etc/passwd')",
            "SELECT set_config('search_path','public',false)",
            "CREATE TABLE public.foo(id int)",
            "CREATE TEMP TABLE foo(id int)",
            "UPDATE uranus_console.event SET uuid=NULL",
            "DELETE FROM uranus_console.event",
            "SET ROLE uranus_console_owner",
        ]:
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await conn.execute(sql)
    finally:
        await conn.close()


async def test_real_streaming_default_max_types_and_transaction(provisioned_console):
    url, _ = provisioned_console
    runtime = runtime_for(url)
    for limit in [50, 500]:
        messages = await collect(runtime, "SELECT i FROM generate_series(1,501) AS i", limit)
        assert messages[-1]["type"] == "complete", messages
        assert messages[-1]["row_count"] == limit
        assert messages[-1]["truncated"]
        assert sum(len(m["rows"]) for m in messages if m["type"] == "rows") == limit
    messages = await collect(
        runtime,
        "SELECT current_user AS identity, current_setting('transaction_read_only') AS readonly, "
        "current_setting('transaction_isolation') AS isolation, "
        "current_setting('statement_timeout') AS timeout, 1.23::numeric AS decimal, "
        "NULL AS nullable, true AS boolean, '2026-09-21'::date AS date",
    )
    row = next(m for m in messages if m["type"] == "rows")["rows"][0]
    assert row == {
        "identity": "uranus_console_reader",
        "readonly": "on",
        "isolation": "repeatable read",
        "timeout": "5s",
        "decimal": "1.23",
        "nullable": None,
        "boolean": True,
        "date": "2026-09-21",
    }
    messages = await collect(
        runtime, "SELECT repeat('😀', 20000) AS big FROM generate_series(1,500)", 500
    )
    assert messages[-1]["truncated"]
    assert messages[-1]["row_count"] < 500
    assert next(m for m in messages if m["type"] == "rows")["rows"][0]["big"]["truncated"]


async def wait_active(observer):
    async with asyncio.timeout(4):
        while not await observer.fetchval(  # noqa: ASYNC110 - observe a real PostgreSQL process
            "SELECT count(*) FROM pg_stat_activity WHERE "
            "application_name='uranus-admin-sql-console' AND state='active' "
            "AND query LIKE 'SELECT sum%'"
        ):
            await asyncio.sleep(0.01)


async def no_console_connections(observer):
    async with asyncio.timeout(2):
        while await observer.fetchval(  # noqa: ASYNC110 - observe a real PostgreSQL process
            "SELECT count(*) FROM pg_stat_activity WHERE "
            "application_name='uranus-admin-sql-console'"
        ):
            await asyncio.sleep(0.01)


@pytest.mark.parametrize("reason", ["cancel", "shutdown", "deadline"])
async def test_real_cancel_releases_db_query(provisioned_console, monkeypatch, reason):
    url, observer_args = provisioned_console
    observer = await asyncpg.connect(**observer_args)
    runtime = runtime_for(url)
    messages = []

    async def send(message):
        messages.append(message)

    if reason == "deadline":
        monkeypatch.setattr("app.sql_console.runtime.DEADLINE_SECONDS", 0.5)
    try:
        task = runtime.start(
            request("SELECT sum(i) FROM generate_series(1,1000000000) AS i"),
            "admin:fixture",
            send,
            AsyncMock(),
        )
        await wait_active(observer)
        if reason == "cancel":
            task.cancel()
        elif reason == "shutdown":
            await runtime.close()
        await task
        await no_console_connections(observer)
        assert messages[-1]["type"] == ("error" if reason == "deadline" else "cancelled")
        if reason == "deadline":
            assert messages[-1]["code"] == "timeout"
        assert not any(m["type"] == "rows" for m in messages)
    finally:
        await runtime.close()
        await observer.close()


async def test_eight_second_deadline_includes_slow_client(provisioned_console):
    url, observer_args = provisioned_console
    observer = await asyncpg.connect(**observer_args)
    runtime = runtime_for(url)
    messages = []

    async def send(message):
        messages.append(message)

    async def never_ack(batch):
        await asyncio.Event().wait()

    try:
        await runtime.execute(
            request("SELECT i FROM generate_series(1,500) AS i", 500),
            "admin:fixture",
            send,
            never_ack,
        )
        assert messages[-1]["type"] == "error"
        assert messages[-1]["code"] == "timeout"
        assert 7900 <= messages[-1]["duration_ms"] < 9500
        assert len([m for m in messages if m["type"] == "rows"]) == 1
        await no_console_connections(observer)
    finally:
        await observer.close()


async def test_statement_timeout_five_seconds(provisioned_console):
    messages = await collect(
        runtime_for(provisioned_console[0]), "SELECT sum(i) FROM generate_series(1,1000000000) AS i"
    )
    assert messages[-1]["code"] == "timeout"
    assert 4900 <= messages[-1]["duration_ms"] < 7000


async def test_real_socket_disconnect_cancels_db(provisioned_console):
    from fastapi import WebSocket

    from app.api.sql_console import console_socket
    from app.auth.service import AdminPrincipal
    from app.main import create_app

    url, observer_args = provisioned_console
    runtime = runtime_for(url)
    app = create_app(runtime.settings)
    app.state.sql_console = runtime
    incoming = asyncio.Queue()
    await incoming.put({"type": "websocket.connect"})
    import json

    await incoming.put(
        {
            "type": "websocket.receive",
            "text": request(
                "SELECT sum(i) FROM generate_series(1,1000000000) AS i"
            ).model_dump_json(),
        }
    )
    sent = []

    async def send(message):
        sent.append(message)

    socket = WebSocket(
        {
            "type": "websocket",
            "app": app,
            "path": "/api/v1/sql-console/ws",
            "headers": [],
            "query_string": b"",
        },
        incoming.get,
        send,
    )
    observer = await asyncpg.connect(**observer_args)
    try:
        with patch(
            "app.api.sql_console.authorize",
            AsyncMock(return_value=AdminPrincipal(subject="admin:fixture", system_admin=True)),
        ):
            task = asyncio.create_task(console_socket(socket))
            await wait_active(observer)
            await incoming.put({"type": "websocket.disconnect", "code": 1000})
            await asyncio.wait_for(task, timeout=2)
        await no_console_connections(observer)
        assert not any(json.loads(m["text"])["type"] == "rows" for m in sent if "text" in m)
    finally:
        await runtime.close()
        await observer.close()
