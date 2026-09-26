"""Safe operator diagnostics against real restricted PostgreSQL roles."""

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.auth.diagnostics import preflight, safe_error
from app.auth.manage import run_command
from app.storage_preflight import StorageIssue


@pytest.mark.parametrize(
    "damage", [None, "select", "insert", "schema", "migration", "owner", "ddl", "domain", "table"]
)
async def test_operator_preflight(admin_store, db_connection, damage):
    await db_connection.execute(text("CREATE ROLE doctor_test NOLOGIN"))
    await db_connection.execute(text("GRANT USAGE ON SCHEMA admin TO doctor_test"))
    await db_connection.execute(text("GRANT SELECT ON admin.alembic_version TO doctor_test"))
    await db_connection.execute(
        text("GRANT SELECT,INSERT,UPDATE ON admin.auth_account TO doctor_test")
    )
    await db_connection.execute(
        text(
            "GRANT SELECT,INSERT,DELETE ON admin.auth_system_admin,admin.auth_journalist "
            "TO doctor_test"
        )
    )
    await db_connection.execute(text("GRANT SELECT,UPDATE ON admin.auth_session TO doctor_test"))
    damage_sql = {
        "select": ["REVOKE SELECT ON admin.auth_account FROM doctor_test"],
        "insert": ["REVOKE INSERT ON admin.auth_account FROM doctor_test"],
        "table": ["ALTER TABLE admin.auth_session RENAME TO hidden_session"],
        "schema": ["ALTER SCHEMA admin RENAME TO unavailable_admin"],
        "migration": ["UPDATE admin.alembic_version SET version_num='outdated'"],
        "owner": [
            "CREATE ROLE doctor_owner_test NOLOGIN",
            "ALTER TABLE admin.auth_account OWNER TO doctor_owner_test",
            "GRANT doctor_owner_test TO doctor_test",
        ],
        "ddl": ["GRANT CREATE ON SCHEMA admin TO doctor_test"],
        "domain": ["GRANT UPDATE ON uranus.venue TO doctor_test"],
    }
    for statement in damage_sql.get(damage, []):
        await db_connection.execute(text(statement))
    await db_connection.execute(text("SET LOCAL ROLE doctor_test"))
    try:
        if damage is None:
            checks = dict(await preflight(db_connection))
            assert checks["Role"] == "doctor_test" and checks["Migration"] == "current"
        else:
            with pytest.raises(StorageIssue):
                await preflight(db_connection)
    finally:
        await db_connection.execute(text("RESET ROLE"))


@pytest.mark.parametrize("failure", ["password", "unreachable"])
async def test_real_connection_failures_are_classified(
    admin_store, database, settings, failure, capsys
):
    url = make_url(database[0]).set(username="admin_history_test", password="secret-do-not-print")
    if failure == "unreachable":
        url = url.set(port=1)
    settings.admin_auth_management_database_url = SecretStr(
        url.render_as_string(hide_password=False)
    )
    with pytest.raises(Exception) as error:
        await run_command(settings, "doctor")
    message = safe_error(error.value)
    assert message == (
        "database authentication failed" if failure == "password" else "database unreachable"
    )
    out = capsys.readouterr()
    assert "secret-do-not-print" not in message + out.out + out.err
    assert "postgresql" not in message + out.out + out.err


async def test_doctor_and_normal_commands_use_preflight_before_password(
    admin_store, database, settings, monkeypatch, capsys
):
    owner = create_async_engine(database[0], hide_parameters=True)
    async with owner.begin() as conn:
        await conn.execute(
            text("CREATE ROLE admin_doctor_test LOGIN PASSWORD 'fixture-doctor-only'")
        )
        await conn.execute(text("GRANT USAGE ON SCHEMA admin TO admin_doctor_test"))
        await conn.execute(text("GRANT SELECT ON admin.alembic_version TO admin_doctor_test"))
        await conn.execute(
            text("GRANT SELECT,INSERT,UPDATE ON admin.auth_account TO admin_doctor_test")
        )
        await conn.execute(
            text(
                "GRANT SELECT,INSERT,DELETE ON admin.auth_system_admin,admin.auth_journalist "
                "TO admin_doctor_test"
            )
        )
        await conn.execute(text("GRANT SELECT,UPDATE ON admin.auth_session TO admin_doctor_test"))
    settings.admin_auth_management_database_url = SecretStr(
        make_url(database[0])
        .set(username="admin_doctor_test", password="fixture-doctor-only")
        .render_as_string(hide_password=False)
    )
    monkeypatch.setattr("app.auth.manage.getpass.getpass", lambda _: "synthetic-operator-password")
    try:
        await run_command(settings, "doctor")
        await run_command(settings, "create", "new-operator", True, True)
        with pytest.raises(ValueError) as error:
            await run_command(settings, "create", "new-operator")
        assert safe_error(error.value) == "account already exists"
        with pytest.raises(ValueError) as error:
            await run_command(settings, "activate", "missing")
        assert safe_error(error.value) == "unknown account"
        output = capsys.readouterr()
        assert "Migration" in output.out and "current" in output.out
        assert "admin_doctor_test" in output.out
        for secret in [
            "fixture-doctor-only",
            "synthetic-operator-password",
            "postgresql+asyncpg://",
        ]:
            assert secret not in output.out + output.err
        settings.admin_auth_management_database_url = None

        def no_prompt(_):
            raise AssertionError("Preflight must precede password prompt")

        monkeypatch.setattr("app.auth.manage.getpass.getpass", no_prompt)
        with pytest.raises(StorageIssue, match="Set ADMIN_AUTH_MANAGEMENT_DATABASE_URL"):
            await run_command(settings, "create", "not-created")
    finally:
        async with owner.begin() as conn:
            await conn.execute(text("DROP OWNED BY admin_doctor_test"))
            await conn.execute(text("DROP ROLE admin_doctor_test"))
        await owner.dispose()


def test_cli_exception_output_never_contains_arbitrary_driver_text(monkeypatch, capsys):
    from app.auth.manage import main

    async def failed(*args):
        raise RuntimeError("postgresql://operator:private-password@host/token-secret")

    monkeypatch.setattr("app.auth.manage.run_command", failed)
    monkeypatch.setattr("sys.argv", ["manage", "doctor"])
    with pytest.raises(SystemExit) as error:
        main()
    captured = capsys.readouterr()
    assert "private-password" not in str(error.value) + captured.out + captured.err
    assert "token-secret" not in str(error.value) + captured.out + captured.err
    assert "run doctor" in str(error.value)


def test_invalid_management_dsn_is_sanitized():
    from app.auth.diagnostics import operator_engine
    from app.config import Settings

    settings = Settings.model_construct(
        admin_auth_management_database_url=SecretStr(
            "postgresql+asyncpg://operator:private-password@localhost:not-a-port/database"
        )
    )
    with pytest.raises(StorageIssue) as error:
        operator_engine(settings)
    assert safe_error(error.value) == "management DSN invalid"
    assert "private-password" not in str(error.value)
