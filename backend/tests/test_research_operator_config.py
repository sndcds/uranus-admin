"""Operator environment isolation without changing normal runtime dotenv behavior."""

import builtins
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.config import Settings
from app.research import areas, population, scope


@pytest.mark.parametrize("module", [areas, population, scope])
@pytest.mark.parametrize("dotenv", ["missing", "unreadable", "conflicting"])
def test_operator_uses_exported_environment_only(module, dotenv, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("NOMINATIM_BASE_URL", "https://provider.test")
    monkeypatch.setenv(
        "ADMIN_AUTH_MANAGEMENT_DATABASE_URL",
        "postgresql+asyncpg://operator@localhost/operator_test",
    )
    if dotenv != "missing":
        (tmp_path / ".env").write_text(
            "NOMINATIM_BASE_URL=https://dotenv.invalid\nLOG_LEVEL=DEBUG\n"
        )
    if dotenv == "unreadable":
        original_open = builtins.open

        def denied(path, *args, **kwargs):
            if Path(path).name == ".env":
                raise PermissionError("Operator cannot read runtime dotenv")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", denied)
        with pytest.raises(PermissionError):
            Settings()
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    run = AsyncMock(return_value={})
    monkeypatch.setattr(module, "configure_logging", lambda _: None)
    if module is scope:
        monkeypatch.setattr(module, "run_scope", run)
        argv = ["scope", "plan", "--region", "DK-81", "--limit", "1"]
    elif module is areas:
        monkeypatch.setattr(module, "run", run)
        argv = ["areas", "plan", "--region", "DE-SH", "--osm-id", "27020"]
    else:
        monkeypatch.setattr(module, "run", run)
        monkeypatch.setattr(module, "population_entries", lambda *_: [])
        argv = ["population", "plan", "unused.xlsx", "--region", "DE-SH"]
    monkeypatch.setattr("sys.argv", argv)
    module.main()
    settings = run.call_args.args[0]
    assert settings.nominatim_base_url == "https://provider.test"
    assert settings.log_level == "INFO"
    assert settings.admin_auth_management_database_url.get_secret_value() == (
        "postgresql+asyncpg://operator@localhost/operator_test"
    )


def test_runtime_settings_still_read_local_dotenv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("NOMINATIM_BASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "test")
    (tmp_path / ".env").write_text("NOMINATIM_BASE_URL=https://provider.test\n")
    assert Settings().nominatim_base_url == "https://provider.test"
    assert Settings(_env_file=None).nominatim_base_url is None
