"""Phase 3 parser/protocol/streaming tests. No live database or credentials."""

import asyncio
import json
import logging
from datetime import UTC, date, datetime, time
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from starlette.testclient import WebSocketDenialResponse
from starlette.websockets import WebSocketDisconnect

from app.auth.service import AdminPrincipal
from app.config import Settings
from app.errors import APIError
from app.main import create_app
from app.sql_console.initial import initial_sql
from app.sql_console.policy import POLICY, ConsoleError, validate_sql
from app.sql_console.protocol import Execute, client_message
from app.sql_console.runtime import ConsoleRuntime
from app.sql_console.serialization import CELL_BYTES, RESULT_BYTES, cell, encode


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM uranus_console.event LIMIT 10;",
        "WITH x AS (SELECT uuid FROM uranus_console.event) SELECT * FROM x",
        "SELECT 1 UNION SELECT 2 INTERSECT SELECT 3 EXCEPT SELECT 4",
        "SELECT CASE WHEN EXISTS (SELECT 1) THEN 'pg_sleep(10)' END",
        "SELECT 'hello'::text, COUNT(*) FROM uranus_console.event",
        "SELECT public.ST_X(public.ST_Point(1,2))",
    ],
)
def test_select_ast(sql):
    validate_sql(sql)


@pytest.mark.parametrize(
    "name", ["ts_stat", "pg_catalog.ts_stat", "TS_STAT", '"ts_stat"', 'pg_catalog."TS_STAT"']
)
@pytest.mark.parametrize("weights", ["", ", 'ab'"])
def test_ts_stat_hidden_query_denied(name, weights):
    sql = (
        f"SELECT * FROM {name}("
        "$$SELECT to_tsvector('simple', query) FROM pg_catalog.pg_stat_activity$$"
        f"{weights})"
    )
    with pytest.raises(ConsoleError) as exc:
        validate_sql(sql)
    assert exc.value.code == "function_denied"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT ts_rewrite('a'::tsquery, "
        "$$SELECT 'a'::tsquery, plainto_tsquery(query) FROM pg_catalog.pg_stat_activity$$)",
        "SELECT pg_catalog.ts_rewrite('a'::tsquery, 'SELECT a, b FROM private_rules')",
        "SELECT \"TS_REWRITE\"('a'::tsquery, 'SELECT a, b FROM private_rules')",
        # The name-based policy intentionally also denies the non-SQL overload.
        "SELECT ts_rewrite('a'::tsquery, 'a'::tsquery, 'b'::tsquery)",
        "WITH x AS (SELECT ts_stat('SELECT secret FROM private_data')) SELECT * FROM x",
        "SELECT (SELECT count(*) FROM pg_catalog.ts_stat(query => 'SELECT secret'))",
    ],
)
def test_nested_dynamic_sql_functions_denied(sql):
    with pytest.raises(ConsoleError) as exc:
        validate_sql(sql)
    assert exc.value.code == "function_denied"


@pytest.mark.parametrize(
    "name",
    [
        "query_to_xml",
        "query_to_xmlschema",
        "query_to_xml_and_xmlschema",
        "table_to_xml",
        "table_to_xmlschema",
        "table_to_xml_and_xmlschema",
        "schema_to_xml",
        "schema_to_xmlschema",
        "schema_to_xml_and_xmlschema",
        "database_to_xml",
        "database_to_xmlschema",
        "database_to_xml_and_xmlschema",
        "cursor_to_xml",
        "cursor_to_xmlschema",
        "pg_stat_get_activity",
        "pg_stat_get_backend_activity",
    ],
)
def test_existing_dynamic_sql_and_activity_guards(name):
    # Raw parsing does not resolve signatures; all overloads must stay denied.
    with pytest.raises(ConsoleError) as exc:
        validate_sql(f"SELECT pg_catalog.\"{name}\"('hidden SQL')")
    assert exc.value.code == "function_denied"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 'ts_stat', $$ts_stat('SELECT query FROM pg_stat_activity')$$",
        "SELECT 'ts_rewrite', 'query_to_xml', 'pg_stat_get_activity'",
        "SELECT 1 AS ts_stat /* ts_stat('hidden SQL') */ -- TS_REWRITE\n",
        "SELECT to_tsvector('simple', 'text'), plainto_tsquery('simple', 'text')",
        "SELECT lower('TS_STAT'), length('ts_stat'), COALESCE(NULL, 'text'), COUNT(*)",
        "SELECT querytree(to_tsquery('simple', 'text')), current_query()",
    ],
)
def test_privacy_guard_preserves_literals_and_safe_functions(sql):
    validate_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_sleep(10)",
        "SELECT query FROM pg_catalog.pg_stat_activity",
        "SELECT query FROM pg_stat_activity",
        "SELECT query FROM pg_stat_get_activity(NULL)",
        "SELECT pg_stat_get_backend_activity(1)",
        "SELECT query_to_xml('SELECT query FROM pg_stat_activity',false,false,'')",
        "SELECT table_to_xml('pg_stat_activity',false,false,'')",
        "SELECT * FROM information_schema.tables",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT set_config('search_path','public',false)",
        'SELECT "pg_catalog"."pg_sleep"(1)',
        "WITH x AS (SELECT pg_sleep(1)) SELECT * FROM x",
        "WITH x AS (DELETE FROM foo RETURNING *) SELECT * FROM x",
        "SELECT 1; SELECT 2",
        "SELECT * INTO new_table FROM foo",
        "SELECT * FROM foo FOR UPDATE",
        "SELECT * FROM foo FOR SHARE",
        'SELECT * FROM uranus."user"',
        "SELECT * FROM admin.auth_account",
        "SELECT $1",
        "SELECT :id",
        "VALUES (1); INSERT INTO foo VALUES(1)",
        "CREATE TABLE foo(id int)",
        "INSERT INTO foo VALUES(1)",
        "UPDATE foo SET id=1",
        "DELETE FROM foo",
        "COPY foo TO STDOUT",
        "SET ROLE postgres",
        "SHOW ALL",
        "CALL proc()",
        "DO $$ BEGIN END $$",
        "VACUUM",
        "ANALYZE foo",
        "TRUNCATE foo",
        "DROP TABLE foo",
        "ALTER TABLE foo ADD a int",
        "NOTIFY chan, 'hi'",
        "LISTEN chan",
        "LOCK foo",
        "PREPARE q AS SELECT 1",
        "EXECUTE q",
        "DEALLOCATE q",
        "DECLARE c CURSOR FOR SELECT 1",
        "FETCH ALL FROM c",
        "MOVE c",
        "CLOSE c",
        "DISCARD ALL",
        "CHECKPOINT",
        "REINDEX TABLE foo",
        "REFRESH MATERIALIZED VIEW foo",
        "GRANT SELECT ON foo TO bar",
        "REVOKE SELECT ON foo FROM bar",
        "CLUSTER foo",
        "RESET ALL",
        "REASSIGN OWNED BY foo TO bar",
        "SECURITY LABEL ON TABLE foo IS NULL",
        "MERGE INTO foo USING bar ON foo.id=bar.id WHEN MATCHED THEN DELETE",
    ],
)
def test_reject_non_queries_and_unsafe_expressions(sql):
    with pytest.raises(ConsoleError):
        validate_sql(sql)


def test_every_contract_deny_and_no_contract_drift():
    contract = json.loads(
        Path("../ansible/roles/uranus_admin/files/sql_console_contract.json").read_text()
    )
    policy = contract["function_policy"]
    signatures = set(policy["custom_functions"])
    names = set(policy["denied_names"])
    names.update(s.split("(")[0].split(".")[-1] for s in policy["custom_functions"])
    for major in policy["catalogs"].values():
        for catalog in major["postgis_versions"].values():
            for value in catalog.values():
                if isinstance(value, dict):
                    signatures.update(value.get("restricted_functions", {}))
                    names.update(
                        s.split("(")[0].split(".")[-1]
                        for s in value.get("restricted_functions", {})
                    )
    assert POLICY == {
        "contract_version": contract["version"],
        "policy_version": policy["version"],
        "names": sorted(names),
        "prefixes": policy["denied_prefixes"],
        "views": list(contract["views"]),
        "signatures": sorted(signatures),
        "denied_names": policy["denied_names"],
    }
    for name in names | {prefix + "fixture" for prefix in policy["denied_prefixes"]}:
        with pytest.raises(ConsoleError, match="function_denied"):
            validate_sql(f'SELECT public."{name}"()')


def test_bound_server_initial_query_keeps_literals():
    sql = "SELECT uuid FROM uranus.event WHERE title='uranus.event :entity_key'"
    result = initial_sql(sql)
    assert "FROM uranus_console.event" in result
    assert "'uranus.event :entity_key'" in result
    assert 'uranus."user"' in initial_sql('SELECT uuid FROM uranus."user"')


def test_sql_byte_limit_before_parser():
    with patch("app.sql_console.policy.parse_sql_json") as parser:
        with pytest.raises(ConsoleError):
            validate_sql("SELECT " + "ä" * 16384)
        parser.assert_not_called()


def test_protocol_strict_bounds():
    value = {"v": 1, "type": "execute", "request_id": str(uuid4()), "sql": "SELECT 1", "params": {}}
    assert client_message.validate_json(json.dumps(value)).row_limit == 50
    for extra in (
        {"v": 2},
        {"row_limit": 501},
        {"row_limit": True},
        {"params": {"id": "secret"}},
        {"token": "secret"},
        {"request_id": "not-uuid"},
    ):
        with pytest.raises(ValidationError):
            client_message.validate_json(json.dumps({**value, **extra}))


@pytest.mark.parametrize("value", ['"\\\n😀' * 20000, "x" * 100000])
def test_serialized_cell_limit_includes_marker(value):
    result = cell(value)
    assert result["truncated"] is True
    assert len(encode(result).encode()) <= CELL_BYTES


def test_safe_scalar_types_no_repr():
    class Secret:
        def __repr__(self):
            raise AssertionError("Never repr unknown values")

    for value in [
        None,
        True,
        12,
        12.5,
        Decimal("1.23"),
        UUID(int=1),
        date.today(),
        datetime.now(UTC),
        time(12, 30),
        "enum-label",
        Secret(),
    ]:
        json.loads(encode(cell(value)))
    assert cell(2**63 - 1) == str(2**63 - 1)
    assert cell(float("nan")) == "nan"


def configured():
    return Settings(
        _env_file=None,
        app_env="test",
        auth_public_origin="http://testserver",
        sql_console_database_url=SecretStr(
            "postgresql://uranus_console_reader:fixture@localhost/unused_test"
        ),
    )


@pytest.mark.parametrize(
    ("cookie", "origin", "identity", "code"),
    [
        (False, "http://testserver", True, 401),
        (True, None, True, 403),
        (True, "http://evil.test", True, 403),
        (True, "http://testserver.evil.test", True, 403),
        (True, "http://testserver", False, 403),
        (True, "http://testserver", True, 101),
    ],
)
def test_websocket_auth_origin(cookie, origin, identity, code):
    app = create_app(configured())
    headers = {"Origin": origin} if origin else {}
    if cookie:
        headers["Cookie"] = "admin_session=" + "a" * 43
    with patch(
        "app.api.sql_console.session_identity",
        AsyncMock(return_value=AdminPrincipal(subject="admin:fixture", system_admin=identity)),
    ):
        with TestClient(app) as client:
            if code == 101:
                with client.websocket_connect("/api/v1/sql-console/ws", headers=headers):
                    pass
            else:
                with pytest.raises(WebSocketDenialResponse) as exc:
                    with client.websocket_connect("/api/v1/sql-console/ws", headers=headers):
                        pytest.fail("Handshake accepted")
                assert getattr(exc.value, "status_code", None) == code


def test_disabled_console_no_dsn_fallback():
    settings = configured()
    settings.sql_console_database_url = None
    app = create_app(settings)
    with patch(
        "app.api.sql_console.session_identity",
        AsyncMock(return_value=AdminPrincipal(subject="admin:fixture", system_admin=True)),
    ):
        with TestClient(app) as client, pytest.raises(WebSocketDenialResponse) as exc:
            with client.websocket_connect(
                "/api/v1/sql-console/ws",
                headers={"Origin": "http://testserver", "Cookie": "admin_session=" + "a" * 43},
            ):
                pytest.fail("Missing DSN accepted")
        assert getattr(exc.value, "status_code", None) == 503


def test_websocket_revalidates_session_and_rejects_url_credentials():
    app = create_app(configured())
    headers = {"Origin": "http://testserver", "Cookie": "admin_session=" + "a" * 43}
    identity = AsyncMock(
        side_effect=[
            AdminPrincipal(subject="admin:fixture", system_admin=True),
            APIError(401, "invalid_credentials", "Expired"),
        ]
    )
    with patch("app.api.sql_console.session_identity", identity), TestClient(app) as client:
        with client.websocket_connect("/api/v1/sql-console/ws", headers=headers) as socket:
            socket.send_json(
                {"v": 1, "type": "execute", "request_id": str(uuid4()), "sql": "SELECT 1"}
            )
            with pytest.raises(WebSocketDisconnect) as exc:
                socket.receive_json()
            assert exc.value.code == 4401
        for suffix in ["?sql=SELECT+1", "?token=secret"]:
            with pytest.raises(WebSocketDenialResponse):
                with client.websocket_connect("/api/v1/sql-console/ws" + suffix, headers=headers):
                    pytest.fail("URL query accepted")


class FakeConnection:
    def __init__(self, count=501, value=1):
        self.remaining, self.value = count, value
        self.transaction_object = AsyncMock()
        self.execute = AsyncMock()
        self.close = AsyncMock()
        self.terminate = lambda: None
        self.fetch_sizes = []

    def transaction(self, **kwargs):
        assert kwargs == {"isolation": "repeatable_read", "readonly": True}
        return self.transaction_object

    async def prepare(self, sql):
        return self

    def get_attributes(self):
        return [type("Attribute", (), {"name": "value"})()]

    async def cursor(self):
        return self

    async def fetch(self, size):
        self.fetch_sizes.append(size)
        if not self.remaining:
            return []
        self.remaining -= 1
        return [(self.value,)]


@pytest.mark.parametrize("limit", [50, 500])
async def test_batched_rows_limits_rollback_and_audit(limit, caplog):
    connection = FakeConnection()
    messages = []
    runtime = ConsoleRuntime(configured())
    request = Execute(
        v=1, type="execute", request_id=uuid4(), sql="SELECT 'sensitive literal'", row_limit=limit
    )

    async def send(message):
        messages.append(message)

    with (
        patch("app.sql_console.runtime.asyncpg.connect", AsyncMock(return_value=connection)),
        patch("app.sql_console.runtime.assert_identity", AsyncMock()),
        caplog.at_level(logging.INFO, logger="admin.sql_console"),
    ):
        await runtime.execute(request, "admin:fixture", send, AsyncMock())
    batches = [m for m in messages if m["type"] == "rows"]
    assert sum(len(m["rows"]) for m in batches) == limit
    assert all(len(m["rows"]) <= 25 for m in batches)
    assert set(connection.fetch_sizes) == {1}
    assert messages[-1]["type"] == "complete"
    assert messages[-1]["truncated"] is True
    connection.transaction_object.rollback.assert_awaited_once()
    connection.transaction_object.commit.assert_not_awaited()
    connection.close.assert_awaited_once()
    assert "sensitive literal" not in caplog.text
    assert caplog.records[-1].row_count == limit


async def test_result_bytes_and_backpressure():
    connection = FakeConnection(value="x" * 16384)
    messages = []
    release = asyncio.Event()

    async def send(message):
        messages.append(message)

    async def acknowledge(batch):
        await release.wait()

    runtime = ConsoleRuntime(configured())
    request = Execute(v=1, type="execute", request_id=uuid4(), sql="SELECT 1", row_limit=500)
    with (
        patch("app.sql_console.runtime.asyncpg.connect", AsyncMock(return_value=connection)),
        patch("app.sql_console.runtime.assert_identity", AsyncMock()),
    ):
        task = runtime.start(request, "admin:fixture", send, acknowledge)
        for _ in range(100):
            await asyncio.sleep(0)
            if any(m["type"] == "rows" for m in messages):
                break
        assert len(connection.fetch_sizes) <= 5
        assert len([m for m in messages if m["type"] == "rows"]) == 1
        release.set()
        await task
    assert messages[-1]["truncated"] is True
    assert sum(len(encode(m).encode()) for m in messages) < RESULT_BYTES


async def test_cancel_shutdown_deadline_and_global_busy(monkeypatch):
    runtime = ConsoleRuntime(configured())
    runtime.settings.sql_console_max_connections = 1
    connection = FakeConnection()
    entered = asyncio.Event()

    async def blocked(sql):
        entered.set()
        await asyncio.Event().wait()

    connection.prepare = blocked
    request = Execute(v=1, type="execute", request_id=uuid4(), sql="SELECT 1")
    for reason in ["cancel", "shutdown", "deadline"]:
        messages = []

        async def send(message, output=messages):
            output.append(message)

        runtime = ConsoleRuntime(runtime.settings)
        entered.clear()
        with (
            patch("app.sql_console.runtime.asyncpg.connect", AsyncMock(return_value=connection)),
            patch("app.sql_console.runtime.assert_identity", AsyncMock()),
        ):
            if reason == "deadline":
                monkeypatch.setattr("app.sql_console.runtime.DEADLINE_SECONDS", 0.02)
            task = runtime.start(request, "admin:fixture", send, AsyncMock())
            await entered.wait()
            with pytest.raises(ConsoleError, match="busy"):
                runtime.start(request, "admin:other", send, AsyncMock())
            if reason == "cancel":
                task.cancel()
            if reason == "shutdown":
                await runtime.close()
            await task
        assert messages[-1]["type"] == ("error" if reason == "deadline" else "cancelled")
        assert connection.transaction_object.rollback.await_count > 0
        assert not [m for m in messages if m["type"] == "rows"]


def test_socket_one_active_query_ack_and_real_cancel_path():
    connection = FakeConnection()
    app = create_app(configured())
    identity = AsyncMock(return_value=AdminPrincipal(subject="admin:fixture", system_admin=True))
    with (
        patch("app.api.sql_console.session_identity", identity),
        patch("app.sql_console.runtime.asyncpg.connect", AsyncMock(return_value=connection)),
        patch("app.sql_console.runtime.assert_identity", AsyncMock()),
        TestClient(app) as client,
    ):
        with client.websocket_connect(
            "/api/v1/sql-console/ws",
            headers={
                "Origin": "http://testserver",
                "Cookie": "admin_session=" + "a" * 43,
            },
        ) as socket:
            first, second = str(uuid4()), str(uuid4())
            socket.send_json({"v": 1, "type": "execute", "request_id": first, "sql": "SELECT 1"})
            assert socket.receive_json()["type"] == "started"
            assert socket.receive_json()["type"] == "columns"
            batch = socket.receive_json()
            assert batch["type"] == "rows" and batch["batch"] == 1
            fetched = len(connection.fetch_sizes)
            socket.send_json({"v": 1, "type": "execute", "request_id": second, "sql": "SELECT 2"})
            assert socket.receive_json() == {
                "v": 1,
                "type": "error",
                "request_id": second,
                "code": "busy",
            }
            assert len(connection.fetch_sizes) == fetched
            socket.send_json({"v": 1, "type": "ack", "request_id": first, "batch": 1})
            assert socket.receive_json()["batch"] == 2
            socket.send_json({"v": 1, "type": "cancel", "request_id": first})
            assert socket.receive_json()["type"] == "cancelled"
            connection.transaction_object.rollback.assert_awaited_once()
            connection.close.assert_awaited_once()


@pytest.mark.parametrize("identity", ["uranus_reader", "admin_user", "postgres"])
async def test_misconfigured_identity_never_connects(identity):
    settings = configured()
    settings.sql_console_database_url = SecretStr(
        f"postgresql://{identity}:fixture@localhost/unused_test"
    )
    messages = []

    async def send(message):
        messages.append(message)

    with patch("app.sql_console.runtime.asyncpg.connect", AsyncMock()) as connect:
        await ConsoleRuntime(settings).execute(
            Execute(v=1, type="execute", request_id=uuid4(), sql="SELECT 1"),
            "admin:fixture",
            send,
            AsyncMock(),
        )
        connect.assert_not_called()
    assert messages[-1]["code"] == "unsafe_identity"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM ts_stat($$SELECT to_tsvector('simple', query) "
        "FROM pg_catalog.pg_stat_activity$$)",
        "SELECT ts_rewrite('a'::tsquery, 'SELECT a, b FROM private_rules')",
    ],
)
async def test_dynamic_sql_rejected_before_connection(sql):
    send = AsyncMock()
    with patch("app.sql_console.runtime.asyncpg.connect", AsyncMock()) as connect:
        await ConsoleRuntime(configured()).execute(
            Execute(v=1, type="execute", request_id=uuid4(), sql=sql),
            "admin:fixture",
            send,
            AsyncMock(),
        )
        connect.assert_not_called()
    send.assert_awaited_once()
    response = send.await_args.args[0]
    assert response["type"] == "error"
    assert response["code"] == "function_denied"


async def test_driver_error_does_not_leak_sql_password_or_repr():
    class UnsafeDriverError(Exception):
        sqlstate = "42601"
        position = "8"

        def __str__(self):
            raise AssertionError("Never stringify a database exception")

    connection = FakeConnection()
    connection.prepare = AsyncMock(side_effect=UnsafeDriverError())
    messages = []

    async def send(message):
        messages.append(message)

    with (
        patch("app.sql_console.runtime.asyncpg.connect", AsyncMock(return_value=connection)),
        patch("app.sql_console.runtime.assert_identity", AsyncMock()),
    ):
        await ConsoleRuntime(configured()).execute(
            Execute(v=1, type="execute", request_id=uuid4(), sql="SELECT 'fixture-secret'"),
            "admin:fixture",
            send,
            AsyncMock(),
        )
    assert messages[-1]["code"] == "syntax_error"
    assert messages[-1]["position"] == 8
    assert "fixture-secret" not in json.dumps(messages)
    connection.transaction_object.rollback.assert_awaited_once()


async def test_deadline_includes_task_scheduling_before_connection():
    from time import perf_counter

    messages = []

    async def send(message):
        await asyncio.sleep(0)
        messages.append(message)

    with patch("app.sql_console.runtime.asyncpg.connect", AsyncMock()) as connect:
        await ConsoleRuntime(configured()).execute(
            Execute(v=1, type="execute", request_id=uuid4(), sql="SELECT 1"),
            "admin:fixture",
            send,
            AsyncMock(),
            submitted_at=perf_counter() - 9,
        )
    connect.assert_not_called()
    assert messages[-1]["code"] == "timeout"


def test_immediate_cancel_without_waiting_for_started():
    connection = FakeConnection()
    with (
        patch(
            "app.api.sql_console.session_identity",
            AsyncMock(return_value=AdminPrincipal(subject="admin:fixture", system_admin=True)),
        ),
        patch("app.sql_console.runtime.asyncpg.connect", AsyncMock(return_value=connection)),
        patch("app.sql_console.runtime.assert_identity", AsyncMock()),
        TestClient(create_app(configured())) as client,
    ):
        with client.websocket_connect(
            "/api/v1/sql-console/ws",
            headers={
                "Origin": "http://testserver",
                "Cookie": "admin_session=" + "a" * 43,
            },
        ) as socket:
            request_id = str(uuid4())
            socket.send_json(
                {"v": 1, "type": "execute", "request_id": request_id, "sql": "SELECT 1"}
            )
            socket.send_json({"v": 1, "type": "cancel", "request_id": request_id})
            messages = []
            for _ in range(4):
                message = socket.receive_json()
                messages.append(message)
                if message["type"] == "cancelled":
                    break
            assert messages[-1]["type"] == "cancelled"
