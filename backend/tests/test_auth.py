import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app

ADMIN_PATHS = [
    "/api/v1/dashboard/summary",
    "/api/v1/findings",
    "/api/v1/quality/venues/missing-geolocation",
]


@pytest.mark.parametrize("path", ADMIN_PATHS)
async def test_all_admin_routes_require_auth(client, path):
    response = await client.get(path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


async def test_bad_development_token(client):
    assert (
        await client.get(ADMIN_PATHS[0], headers={"Authorization": "Bearer wrong"})
    ).status_code == 401


async def test_default_auth_fails_closed():
    app = create_app(Settings(_env_file=None))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            ADMIN_PATHS[0], headers={"Authorization": "Bearer unverified-jwt"}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"
        assert (await client.get("/docs")).status_code == 404
        assert (await client.get("/openapi.json")).status_code == 404


@pytest.mark.parametrize(
    "extra",
    [
        {"dev_auth_enabled": True},
        {"app_debug": True},
        {"openapi_enabled": True},
        {"cors_origins": "*"},
    ],
)
@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_unsafe_production_config_rejected(extra, app_env):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env=app_env, **extra)


async def test_openapi(client):
    import asyncio
    import json
    from pathlib import Path

    schema = (await client.get("/openapi.json")).json()
    assert schema == json.loads(
        await asyncio.to_thread(Path("../frontend/docs/openapi.json").read_text)
    )
    for path in ADMIN_PATHS:
        operation = schema["paths"][path]["get"]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["summary"] and operation["description"]
        assert "401" in operation["responses"]
        assert operation["responses"]["422"]["content"]["application/json"]["schema"][
            "$ref"
        ].endswith("ErrorResponse")


async def test_cors_restricts_origins(settings):
    settings.cors_origins = "https://admin.example.invalid"
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for origin, expected in [
            ("https://admin.example.invalid", 200),
            ("https://evil.invalid", 400),
        ]:
            response = await client.options(
                "/api/v1/findings",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Authorization",
                },
            )
            assert response.status_code == expected


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/v1/dashboard/activity"),
        ("GET", "/api/v1/work-queues/partner_requests"),
        ("GET", "/api/v1/work-queues/team_invitations"),
        ("GET", "/api/v1/work-queues/user_activation"),
        ("GET", "/api/v1/check-runs"),
        ("POST", "/api/v1/check-runs"),
        ("PATCH", "/api/v1/finding-reviews"),
    ],
)
async def test_new_routes_are_fail_closed(client, method, path):
    response = await client.request(method, path)
    assert response.status_code == 401


async def test_storage_disabled_does_not_enable_writes(client, headers):
    response = await client.get("/api/v1/check-runs", headers=headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "admin_storage_unconfigured"


@pytest.mark.parametrize(
    "extra",
    [
        {"auth_public_origin": "http://admin.example.test"},
        {"auth_public_origin": "https://admin.example.test/login"},
        {"auth_public_origin": "https://user:secret@admin.example.test"},
        {"auth_public_origin": "https://*.example.test"},
        {"auth_public_origin": "https://admin.example.test?token=secret"},
        {"auth_session_seconds": 300, "auth_idle_seconds": 900},
        {"auth_session_seconds": 999999},
        {"admin_auth_management_database_url": "sqlite:///auth.db"},
    ],
)
def test_production_auth_configuration_rejects_unsafe_values(extra):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production", **extra)
