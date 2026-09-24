"""Provenance tests use only guarded disposable fixture databases and synthetic rows."""

import json
import logging
import traceback
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.admin_tables import finding
from app.errors import APIError
from app.main import create_app
from app.repositories.query import ReadQuery
from app.sql_diagnostics.provenance.registry import COVERAGE, MODELS, build
from app.sql_diagnostics.provenance.render import bounded, render, select_only
from app.sql_diagnostics.provenance.service import definition, execute
from app.sql_diagnostics.readonly import read_registered_rows, readonly_connection
from tests.conftest import uid

STAMP = datetime(2026, 10, 1, tzinfo=UTC)
SECRET = "TOP-SECRET"


def parameters(view, **extra):
    values = {"as_of": STAMP}
    if view.endswith(".detail") or view == "geo.area":
        values["id"] = uid(20)
    if view == "graph":
        values.update(root_type="venue", root_key=uid(20))
    if view == "search":
        values.update(q="synthetic")
    elif view.endswith("search"):
        values.update(q="synthetic", entity_type="venue")
    return MODELS[view].model_validate(values | extra)


def test_machine_readable_coverage_and_frontend_registry():
    enabled = [row["view_id"] for row in COVERAGE if row["sql_capable"]]
    assert set(enabled) == set(MODELS)
    assert len(enabled) == len(set(enabled))
    frontend = json.loads(Path("../frontend/shared/provenance-views.json").read_text())
    assert frontend == {key: list(model.model_fields) for key, model in MODELS.items()}


@pytest.mark.parametrize("view", MODELS)
def test_every_definition_is_pure_registered_and_safe(view, settings):
    result = definition(view, parameters(view), settings)
    assert result.sources
    ids = [source.id for source in result.sources]
    assert len(ids) == len(set(ids))
    for source in result.sources:
        assert source.id.startswith(view + ".")
        assert source.readonly
        select_only(source.sql)
        assert not {
            "password_hash",
            "accept_token",
            "api_import_token",
            "activate_token",
            "password_reset_token",
            "payload",
            "metadata",
            "snapshot",
        } & set(source.columns)
        assert source.executable == (not source.dependencies)
        assert (source.copy_sql is not None) == source.executable
    assert result.post_processing and result.observed_at == STAMP
    with pytest.raises(ValueError):
        parameters(view, sql="SELECT 1")


def test_dashboard_runtime_groups_and_parameters(settings):
    result = definition("dashboard", parameters("dashboard", severity="error"), settings)
    by_id = {source.id: source for source in result.sources}
    assert len(by_id) == 8
    assert {source.datasource for source in result.sources} == {"uranus", "admin"}
    assert "resolved" in by_id["dashboard.quality_counts"].parameters.values()
    assert "resolved" in by_id["dashboard.preview_records"].parameters.values()
    assert "error" in by_id["dashboard.preview_records"].parameters.values()
    assert 4 in by_id["dashboard.preview_records"].parameters.values()
    assert any("period_window" in item for item in result.post_processing)
    assert any("Dringend" in item for item in result.post_processing)
    assert any("success" in str(item.parameters) for item in result.sources)
    assert by_id["dashboard.new_records"].parameters["end_at"] == "2026-10-01T00:00:00"


@pytest.mark.parametrize(
    "view,filters,expected",
    [
        ("activity", {"entity_type": "venue", "page": 3, "page_size": 10}, ["venue", 20, 10]),
        (
            "findings",
            {"severity": "error", "active_only": True, "page": 3, "page_size": 10},
            ["error", "resolved", 20, 10],
        ),
        ("venues", {"q": "Hafen", "page": 3, "page_size": 10}, ["%Hafen%", 20, 10]),
        (
            "queues.partner_requests",
            {"status": "pending", "page": 3, "page_size": 10},
            ["pending", 20, 10],
        ),
    ],
)
def test_filters_reuse_runtime_queries(view, filters, expected, settings):
    result = definition(view, parameters(view, **filters), settings)
    values = [value for source in result.sources for value in source.parameters.values()]
    for item in expected:
        assert item in values


def test_geo_and_live_do_not_claim_fabricated_parameters(settings):
    result = definition("findings", parameters("findings", geo_scope_id=uid(99)), settings)
    assert any("membership_scan" in source.id for source in result.sources)
    assert any(source.datasource == "uranus" and source.dependencies for source in result.sources)
    assert any("Membership" in item for item in result.post_processing)
    live = definition("findings", parameters("findings", mode="live"), settings)
    assert len(live.sources) >= 19
    assert any("keine Live-Findings" in item for item in live.post_processing)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM admin.finding",
        "SELECT 1; SELECT 2",
        "WITH x AS (DELETE FROM admin.finding RETURNING id) SELECT id FROM x",
        "SELECT 1 INTO scratch",
        "SELECT 1 FOR UPDATE",
    ],
)
def test_registered_statement_guard(sql):
    with pytest.raises(ValueError):
        select_only(sql)


async def test_all_registered_queries_execute_against_synthetic_schema(
    database, admin_store, settings
):
    # Same fixture engine can read both fixture schemas. Production selection is
    # tested independently below; this validates every runtime SQL projection.
    engine = create_async_engine(database[0], poolclass=NullPool, hide_parameters=True)
    try:
        for view in MODELS:
            for source in build(view, parameters(view), settings, STAMP):
                if source.id == "notifications.source_configuration":
                    # This optional source column is deliberately absent from the
                    # base fixture. Capability/dependency guard forbids execution.
                    assert source.dependencies
                    continue
                query = bounded(source.rendered.query)
                async with readonly_connection(engine) as connection:
                    async with connection.stream(query.statement, query.parameters) as stream:
                        assert set(stream.keys()) == set(source.rendered.columns), source.id
                        rows = await stream.mappings().fetchmany(50)
                if not source.dependencies:
                    async with readonly_connection(engine) as connection:
                        copied = await connection.exec_driver_sql(source.rendered.copy_sql)
                        assert set(copied.keys()) == set(source.rendered.columns), source.id
                assert len(rows) <= 50, source.id
                for row in rows:
                    assert set(row) == set(source.rendered.columns), source.id
    finally:
        await engine.dispose()


async def test_shared_executor_admin_write_fails_and_rollback_settings(database, admin_store):
    # The actual fixture admin runtime role has INSERT/UPDATE privileges.
    engine = admin_store.engine
    rollbacks = []
    event.listen(engine.sync_engine, "rollback", lambda conn: rollbacks.append(True))
    async with readonly_connection(engine) as connection:
        values = (
            await connection.execute(
                text(
                    "SELECT current_setting('transaction_read_only'), "
                    "current_setting('transaction_isolation'), "
                    "current_setting('statement_timeout'), "
                    "current_setting('lock_timeout'), "
                    "current_setting('idle_in_transaction_session_timeout')"
                )
            )
        ).one()
        assert tuple(values) == ("on", "repeatable read", "5s", "1s", "10s")
    with pytest.raises(DBAPIError) as error:
        async with readonly_connection(engine) as connection:
            await connection.execute(text("UPDATE admin.finding SET message='forbidden'"))
    assert error.value.orig.sqlstate == "25006"
    assert len(rollbacks) == 2


async def test_bounded_stream_and_safe_literal_copy(database):
    engine = create_async_engine(database[0], poolclass=NullPool)
    try:
        query = render(ReadQuery(text("SELECT value FROM generate_series(1, 1000) value")))
        rows, _ = await read_registered_rows(engine, bounded(query.query))
        assert len(rows) == 50
        for limit in (0, 101):
            with pytest.raises(ValueError):
                bounded(query.query, limit)
        value = "synthetic'; SELECT 'escaped"
        query = render(ReadQuery(text("SELECT :value AS value"), {"value": value}), ("value",))
        assert value not in query.sql
        async with engine.connect() as connection:
            assert (await connection.exec_driver_sql(query.copy_sql)).scalar_one() == value
    finally:
        await engine.dispose()


async def test_safe_projection_secrets_and_datasource_selection(settings, caplog):
    query = render(ReadQuery(select(finding)))
    assert "metadata" not in query.columns
    engines = SimpleNamespace(engine=object(), admin_engine=object())
    request = SimpleNamespace(app=SimpleNamespace(state=engines))
    caplog.set_level(logging.INFO, logger="admin.sql_provenance")
    for view, source, expected in [
        ("dashboard", "dashboard.new_records", engines.engine),
        ("checks", "checks.records", engines.admin_engine),
    ]:
        with patch(
            "app.sql_diagnostics.provenance.service.read_registered_rows", new_callable=AsyncMock
        ) as reader:
            reader.return_value = ([], STAMP)
            result = await execute(
                request, view, source, parameters(view), settings, "admin:fixture"
            )
            assert reader.call_args.args[0] is expected
            assert reader.call_args.kwargs["admin_boundary"] == (source.startswith("checks."))
            assert result.row_count == 0
            reader.side_effect = RuntimeError(SECRET)
            with pytest.raises(APIError) as error:
                await execute(request, view, source, parameters(view), settings, "admin:fixture")
            assert SECRET not in "".join(traceback.format_exception(error.value)) + caplog.text
    with patch(
        "app.sql_diagnostics.provenance.service.read_registered_rows", new_callable=AsyncMock
    ) as reader:
        with pytest.raises(APIError):
            await execute(
                request,
                "checks",
                "dashboard.new_records",
                parameters("checks"),
                settings,
                "admin:fixture",
            )
        reader.assert_not_called()


async def test_api_auth_typed_filters_and_no_automatic_execution(settings, headers):
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        path = "/api/v1/sql-provenance/dashboard"
        assert (await client.get(path)).status_code == 401
        with patch(
            "app.sql_diagnostics.provenance.service.read_registered_rows", new_callable=AsyncMock
        ) as reader:
            result = await client.get(path, headers=headers, params={"period": "7d"})
            assert result.status_code == 200, result.text
            reader.assert_not_called()
            for params in (
                {"sql": "SELECT 1"},
                {"period": "bad"},
                [("period", "7d"), ("period", "24h")],
            ):
                assert (await client.get(path, headers=headers, params=params)).status_code == 422
            for body in ({"sql": "SELECT 1"}, {"table": "finding"}, {"column": "password_hash"}):
                assert (
                    await client.post(
                        path + "/dashboard.new_records/execute", headers=headers, json=body
                    )
                ).status_code == 422
            reader.assert_not_called()
            assert (
                await client.get("/api/v1/sql-provenance/not-registered", headers=headers)
            ).status_code == 404


def test_real_keyset_cursor_uses_runtime_scope_and_conditions(settings):
    from app.schemas.cursor import FindingCursor, encode, scope
    from app.schemas.finding import FindingFilters

    filters = FindingFilters(active_only=True, severity="error", cursor="start")
    token = encode(FindingCursor(scope=scope(filters), priority_score=70, id="synthetic-key"))
    result = definition(
        "findings",
        parameters("findings", active_only=True, severity="error", cursor=token),
        settings,
    )
    records = next(item for item in result.sources if item.id == "findings.records")
    assert "synthetic-key" in records.parameters.values()
    assert 70 in records.parameters.values()
    assert "OFFSET 0" in records.copy_sql
    with pytest.raises(APIError):
        definition(
            "findings",
            parameters("findings", active_only=False, severity="error", cursor=token),
            settings,
        )


async def test_provenance_cookie_auth_and_csrf_boundary(settings):
    from app.auth.service import AdminPrincipal

    settings.auth_public_origin = "http://test"
    app = create_app(settings)
    path = "/api/v1/sql-provenance/checks/checks.records/execute"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post(path, json={})).status_code == 401
        client.cookies.set(settings.session_cookie, "x" * 43)
        with (
            patch("app.auth.dependencies.session_identity", new_callable=AsyncMock) as identity,
            patch("app.api.sql_provenance.execute", new_callable=AsyncMock) as run,
        ):
            identity.return_value = AdminPrincipal(subject="admin:fixture", system_admin=True)
            for extra in (
                {},
                {"Origin": "http://evil.invalid", "X-Admin-CSRF": "1"},
                {"Origin": "http://test"},
            ):
                response = await client.post(path, headers=extra, json={})
                assert response.status_code == 403
                assert response.json()["error"]["code"] == "csrf_rejected"
            identity.return_value = AdminPrincipal(subject="admin:fixture", system_admin=False)
            response = await client.post(
                path, headers={"Origin": "http://test", "X-Admin-CSRF": "1"}, json={}
            )
            assert response.status_code == 403
            run.assert_not_called()


async def test_secret_source_fixture_and_admin_payload_never_return(
    database, admin_store, settings, caplog
):
    engine = create_async_engine(database[0], poolclass=NullPool, hide_parameters=True)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(engine=engine, admin_engine=admin_store.engine))
    )
    try:
        async with engine.begin() as connection:
            # Guarded synthetic fixture setup, not runtime domain writes.
            await connection.execute(
                text('UPDATE uranus."user" SET password_hash=:secret'), {"secret": SECRET}
            )
        await admin_store.execute(
            finding.insert().values(
                id="provenance-secret",
                rule="synthetic",
                entity_type="venue",
                entity_key=str(uid(20)),
                field="point",
                status="open",
                severity="error",
                message="Synthetic",
                first_seen_at=STAMP,
                last_seen_at=STAMP,
                metadata={"password_hash": SECRET, "accept_token": SECRET},
            )
        )
        await admin_store.commit()
        for view, source in [("users", "users.records"), ("findings", "findings.records")]:
            result = await execute(
                request, view, source, parameters(view), settings, "admin:fixture"
            )
            assert result.row_count > 0
            public = (
                definition(view, parameters(view), settings).model_dump_json()
                + result.model_dump_json()
            )
            assert SECRET not in public + caplog.text + repr(result)
    finally:
        await engine.dispose()


async def test_optional_configuration_is_not_executable_without_capability(settings):
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(engine=None, admin_engine=None))
    )
    with patch(
        "app.sql_diagnostics.provenance.service.read_registered_rows", new_callable=AsyncMock
    ) as reader:
        with pytest.raises(APIError) as error:
            await execute(
                request,
                "notifications",
                "notifications.source_configuration",
                parameters("notifications"),
                settings,
                "admin:fixture",
            )
        assert error.value.status == 409
        assert error.value.code == "provenance_dependency"
        reader.assert_not_called()


def test_venue_scope_provenance_uses_bound_filter_on_count_and_records(settings):
    for scope in ("organization", "shared"):
        result = definition("venues", parameters("venues", scope=scope), settings)
        sources = {source.id: source for source in result.sources}
        for key in ("venues.count", "venues.records"):
            assert sources[key].parameters["scope"] == scope
            assert "a.venue_scope=:scope" in sources[key].sql
        assert result.parameters["scope"] == scope
        assert f"scope={scope}" in result.endpoint
    spaces = definition("spaces", parameters("spaces", scope="shared"), settings)
    assert all("scope" not in source.parameters for source in spaces.sources)
