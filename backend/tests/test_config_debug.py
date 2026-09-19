import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def isolated_settings_environment(monkeypatch):
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)


@pytest.mark.parametrize("app_env", ["staging", "production"])
@pytest.mark.parametrize("opt_in", [None, False])
def test_debug_requires_explicit_production_opt_in(app_env, opt_in):
    extra = {} if opt_in is None else {"allow_production_debug": opt_in}
    with pytest.raises(
        ValidationError, match="Production debug requires ALLOW_PRODUCTION_DEBUG=true"
    ):
        Settings(_env_file=None, app_env=app_env, app_debug=True, **extra)


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_debug_with_production_opt_in(app_env):
    settings = Settings(
        _env_file=None, app_env=app_env, app_debug=True, allow_production_debug=True
    )
    assert settings.app_debug
    assert settings.allow_production_debug
    assert not settings.dev_auth_enabled
    assert not settings.openapi_enabled
    assert settings.session_cookie == "__Host-admin_session"


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_local_debug_needs_no_second_opt_in(app_env):
    settings = Settings(_env_file=None, app_env=app_env, app_debug=True)
    assert settings.app_debug
    assert not settings.allow_production_debug


@pytest.mark.parametrize("app_env", ["staging", "production"])
@pytest.mark.parametrize("field", ["dev_auth_enabled", "openapi_enabled"])
def test_production_opt_in_does_not_enable_development_features(app_env, field):
    with pytest.raises(
        ValidationError, match="Development auth and public OpenAPI require development/test"
    ):
        Settings(
            _env_file=None,
            app_env=app_env,
            app_debug=True,
            allow_production_debug=True,
            dev_admin_token=SecretStr("synthetic-development-token-at-least-32-characters"),
            **{field: True},
        )


@pytest.mark.parametrize("app_env", ["staging", "production"])
@pytest.mark.parametrize(
    "field,message",
    [
        ("auth_public_origin", "Production authentication requires an HTTPS origin"),
        ("nominatim_base_url", "Production Nominatim requires HTTPS"),
        ("kulturbytes_app_public_base_url", "Notification recipient links require HTTPS"),
    ],
)
def test_production_opt_in_preserves_https_requirements(app_env, field, message):
    with pytest.raises(ValidationError, match=message):
        Settings(
            _env_file=None,
            app_env=app_env,
            app_debug=True,
            allow_production_debug=True,
            **{field: "http://service.example.test"},
        )


def test_debug_defaults_are_disabled():
    settings = Settings(_env_file=None)
    assert settings.app_env == "production"
    assert not settings.app_debug
    assert not settings.allow_production_debug


def test_opt_in_alone_does_not_enable_debug():
    settings = Settings(_env_file=None, allow_production_debug=True)
    assert not settings.app_debug


def test_production_debug_environment_variables(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_DEBUG", "true")
    monkeypatch.setenv("ALLOW_PRODUCTION_DEBUG", "false")
    with pytest.raises(
        ValidationError, match="Production debug requires ALLOW_PRODUCTION_DEBUG=true"
    ):
        Settings(_env_file=None)
    monkeypatch.setenv("ALLOW_PRODUCTION_DEBUG", "true")
    settings = Settings(_env_file=None)
    assert settings.app_debug
    assert settings.allow_production_debug


@pytest.mark.parametrize("app_env", ["staging", "production"])
async def test_production_debug_keeps_http_debug_and_public_docs_disabled(app_env):
    app = create_app(
        Settings(_env_file=None, app_env=app_env, app_debug=True, allow_production_debug=True)
    )
    assert app.debug is False
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        for path in ("/docs", "/openapi.json", "/redoc"):
            assert (await client.get(path)).status_code == 404
        assert (await client.get("/api/v1/findings")).status_code == 401
