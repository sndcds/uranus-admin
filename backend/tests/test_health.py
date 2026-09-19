import json
import logging

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from app.config import Settings
from app.database import get_connection
from app.main import create_app


async def test_health_without_database(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_failure_is_sanitized(settings, caplog):
    settings.database_url = SecretStr("postgresql+asyncpg://secret:private@localhost/missing")
    app = create_app(settings)

    async def unavailable():
        raise OSError("password=private token=sensitive")
        yield

    app.dependency_overrides[get_connection] = unavailable
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert "private" not in response.text + caplog.text
    assert "sensitive" not in response.text + caplog.text


async def test_ready_real_database(db_client):
    response = await db_client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_unexpected_error_does_not_escape_to_server_logs(settings, caplog):
    app = create_app(settings)

    async def unexpected():
        raise ValueError("private-token-must-not-escape")
        yield

    app.dependency_overrides[get_connection] = unexpected
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=True), base_url="http://test"
    ) as client:
        response = await client.get("/ready")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "private-token" not in response.text + caplog.text


@pytest.mark.parametrize(
    "app_env,debug",
    [
        ("development", True),
        ("test", True),
        ("development", False),
        ("production", False),
        ("staging", True),
        ("production", True),
    ],
)
@pytest.mark.parametrize(
    "error_type,status", [(ProgrammingError, 503), (OSError, 503), (ValueError, 500)]
)
async def test_exception_details_only_in_debug_server_logs(
    settings, capsys, monkeypatch, app_env, debug, error_type, status
):
    # Lifespan configures real JSON logging; restore global logger state after the test.
    for name, attributes in {
        "admin": ("handlers", "level", "propagate"),
        "sqlalchemy.engine": ("level",),
        "uvicorn.access": ("disabled",),
    }.items():
        logger = logging.getLogger(name)
        for attribute in attributes:
            monkeypatch.setattr(logger, attribute, getattr(logger, attribute))
    settings.app_env = app_env
    settings.app_debug = debug
    settings.allow_production_debug = app_env in {"staging", "production"}
    settings.log_level = "DEBUG"
    settings.dev_auth_enabled = False
    settings.openapi_enabled = False
    settings = Settings.model_validate(settings.model_dump())
    app = create_app(settings)

    async def failing_connection():
        if error_type is ProgrammingError:
            raise ProgrammingError(
                "SELECT missing_column", {}, Exception("debug-only-error-detail")
            )
        raise error_type("debug-only-error-detail")
        yield

    app.dependency_overrides[get_connection] = failing_connection
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=True), base_url="http://test"
        ) as client:
            response = await client.get("/ready")

    assert response.status_code == status
    assert response.json()["error"]["code"] == (
        "database_unavailable" if status == 503 else "internal_error"
    )
    assert "debug-only-error-detail" not in response.text
    assert "Traceback" not in response.text
    assert "missing_column" not in response.text
    output = capsys.readouterr().err
    records = [json.loads(line) for line in output.splitlines()]
    errors = [record for record in records if record["level"] == "ERROR"]
    assert errors
    for error in errors:
        assert error["error_type"] == error_type.__name__
        if debug:
            assert "debug-only-error-detail" in error["traceback"]
            assert "Traceback (most recent call last)" in error["traceback"]
            assert "failing_connection" in error["traceback"]
        else:
            assert "traceback" not in error
    if not debug:
        assert "debug-only-error-detail" not in output
        assert "missing_column" not in output


@pytest.mark.integration
async def test_missing_database_returns_503(database, settings):
    settings.database_url = SecretStr(
        make_url(database[0])
        .set(database="kulturbytes_missing_database")
        .render_as_string(hide_password=False)
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=True), base_url="http://test"
        ) as client:
            response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert "kulturbytes_missing_database" not in response.text


@pytest.mark.parametrize(
    "app_env,debug",
    [
        ("development", True),
        ("test", True),
        ("development", False),
        ("production", False),
        ("staging", True),
        ("production", True),
    ],
)
async def test_api_503_logs_code_and_debug_traceback(settings, capsys, monkeypatch, app_env, debug):
    from app.errors import APIError

    for name, attributes in {
        "admin": ("handlers", "level", "propagate"),
        "sqlalchemy.engine": ("level",),
        "uvicorn.access": ("disabled",),
    }.items():
        logger = logging.getLogger(name)
        for attribute in attributes:
            monkeypatch.setattr(logger, attribute, getattr(logger, attribute))
    settings.app_env = app_env
    settings.app_debug = debug
    settings.allow_production_debug = app_env in {"staging", "production"}
    settings.dev_auth_enabled = False
    settings.openapi_enabled = False
    # ERROR logging must work at the normal INFO level too.
    settings.log_level = "INFO"
    settings = Settings.model_validate(settings.model_dump())
    app = create_app(settings)

    async def rejected_connection():
        try:
            raise RuntimeError("debug-only-internal-cause")
        except RuntimeError as cause:
            raise APIError(
                503, "admin_storage_unconfigured", "Admin storage requires a restricted role."
            ) from cause
        yield

    app.dependency_overrides[get_connection] = rejected_connection
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/ready?secret=private-query", headers={"Authorization": "Bearer private-token"}
            )
    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "admin_storage_unconfigured",
            "message": "Admin storage requires a restricted role.",
        }
    }
    assert "Traceback" not in response.text and "debug-only-internal-cause" not in response.text
    output = capsys.readouterr().err
    records = [json.loads(line) for line in output.splitlines()]
    errors = [record for record in records if record["level"] == "ERROR"]
    assert len(errors) == 1
    error = errors[0]
    assert error["event"] == "admin_storage_unconfigured"
    assert error["error_type"] == "APIError"
    assert error["status_code"] == 503 and error["method"] == "GET" and error["route"] == "/ready"
    if debug:
        assert "Traceback (most recent call last)" in error["traceback"]
        assert "rejected_connection" in error["traceback"]
        assert "Admin storage requires a restricted role." in error["traceback"]
        assert "debug-only-internal-cause" in error["traceback"]
    else:
        assert "traceback" not in error
        assert "debug-only-internal-cause" not in output
    assert "private-query" not in output and "private-token" not in output


@pytest.mark.parametrize(
    "damage", [None, "migration", "table", "grant", "unsafe", "schema", "down"]
)
async def test_admin_readiness_is_read_only_and_fail_closed(
    admin_store, database, settings, damage
):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    if damage is None:
        from app.storage_preflight import RUNTIME_GRANTS, check_grants, check_schema

        async with admin_store.begin():
            await check_schema(admin_store)
            await check_grants(admin_store, RUNTIME_GRANTS)
    owner = create_async_engine(database[0], hide_parameters=True)
    settings.database_url = SecretStr(database[0])
    settings.app_env = "production"
    settings.dev_auth_enabled = False
    settings.openapi_enabled = False
    # Reversible committed changes are restored before fixture cleanup.
    changes = {
        "migration": ("UPDATE admin.alembic_version SET version_num='old'", None),
        "table": (
            "ALTER TABLE admin.auth_account RENAME TO hidden_account",
            "ALTER TABLE admin.hidden_account RENAME TO auth_account",
        ),
        "grant": (
            "REVOKE INSERT ON admin.auth_session FROM admin_history_test",
            "GRANT INSERT ON admin.auth_session TO admin_history_test",
        ),
        "unsafe": (
            "GRANT CREATE ON SCHEMA admin TO admin_history_test",
            "REVOKE CREATE ON SCHEMA admin FROM admin_history_test",
        ),
        "schema": (
            "ALTER SCHEMA admin RENAME TO hidden_admin",
            "ALTER SCHEMA hidden_admin RENAME TO admin",
        ),
    }
    if damage in changes:
        async with owner.begin() as conn:
            await conn.execute(text(changes[damage][0]))
    if damage == "down":
        settings.admin_database_url = SecretStr(
            "postgresql+asyncpg://test:synthetic@127.0.0.1:1/unavailable"
        )
    try:
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                result = await client.get("/ready")
                assert result.status_code == (200 if damage is None else 503)
                assert "synthetic" not in result.text
                assert (await client.get("/health")).status_code == 200
    finally:
        if damage in changes and changes[damage][1]:
            async with owner.begin() as conn:
                await conn.execute(text(changes[damage][1]))
        await owner.dispose()


async def test_production_requires_admin_storage(db_client, settings):
    settings.app_env = "production"
    assert (await db_client.get("/ready")).status_code == 503
