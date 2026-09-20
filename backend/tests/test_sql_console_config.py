"""The infrastructure capability never adopts another runtime identity."""

from app.config import Settings


def test_console_secret_has_no_source_or_admin_fallback(monkeypatch):
    monkeypatch.delenv("SQL_CONSOLE_DATABASE_URL", raising=False)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+asyncpg://uranus_reader:source-fixture@localhost/oklab",
        admin_database_url="postgresql+asyncpg://admin_user:admin-fixture@localhost/oklab",
    )
    assert settings.sql_console_database_url is None


def test_explicit_console_secret_stays_separate_and_masked(monkeypatch):
    value = "postgresql+asyncpg://uranus_console_reader:console-fixture@localhost/oklab"
    monkeypatch.setenv("SQL_CONSOLE_DATABASE_URL", value)
    settings = Settings(_env_file=None, app_env="test")
    assert settings.sql_console_database_url is not None
    assert settings.sql_console_database_url.get_secret_value() == value
    assert "console-fixture" not in repr(settings)
    assert "console-fixture" not in settings.model_dump_json()
