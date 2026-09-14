import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.engine import make_url

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
