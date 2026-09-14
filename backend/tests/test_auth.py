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
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "admin_auth_unconfigured"
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
def test_unsafe_production_config_rejected(extra):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **extra)


async def test_openapi(client):
    schema = (await client.get("/openapi.json")).json()
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
