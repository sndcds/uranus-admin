import asyncio
import io

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url


def test_offline_bootstrap_precedes_version_table(monkeypatch):
    monkeypatch.setenv(
        "ADMIN_MIGRATION_DATABASE_URL",
        "postgresql+asyncpg://unused:unused@localhost/unused_test",
    )
    output = io.StringIO()
    command.upgrade(Config("alembic.ini", output_buffer=output), "head", sql=True)
    sql = output.getvalue()
    assert sql.index("BEGIN;") < sql.index("CREATE SCHEMA admin")
    assert sql.index("CREATE SCHEMA admin") < sql.index("CREATE TABLE admin.alembic_version")
    assert "AUTHORIZATION CURRENT_USER" in sql
    assert "REVOKE ALL PRIVILEGES ON SCHEMA admin FROM PUBLIC" in sql
    assert sql.rstrip().endswith("COMMIT;")


def test_migration_still_requires_explicit_migrator(monkeypatch):
    monkeypatch.delenv("ADMIN_MIGRATION_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused@localhost/unused_test")
    with pytest.raises(RuntimeError, match="Set ADMIN_MIGRATION_DATABASE_URL explicitly"):
        command.upgrade(Config("alembic.ini", output_buffer=io.StringIO()), "head", sql=True)


@pytest.mark.integration
async def test_existing_schema_owner_and_grants_are_preserved(database, monkeypatch):
    url = make_url(database[0])
    conn = await asyncpg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False)
    )
    assert not await conn.fetchval("SELECT to_regnamespace('admin')")
    assert not await conn.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='bootstrap_migrator_test')"
    )
    schema_sql = "SELECT nspowner, nspacl::text FROM pg_namespace WHERE nspname='admin'"
    try:
        await conn.execute(
            "CREATE ROLE bootstrap_migrator_test LOGIN PASSWORD 'fixture-bootstrap-only'"
        )
        # Operator owns this pre-existing schema; migrator owns only its tables.
        await conn.execute("CREATE SCHEMA admin")
        await conn.execute("GRANT USAGE, CREATE ON SCHEMA admin TO bootstrap_migrator_test")
        before = await conn.fetchrow(schema_sql)
        monkeypatch.setenv(
            "ADMIN_MIGRATION_DATABASE_URL",
            url.set(
                username="bootstrap_migrator_test", password="fixture-bootstrap-only"
            ).render_as_string(hide_password=False),
        )
        config = Config("alembic.ini")
        await asyncio.to_thread(command.upgrade, config, "head")
        await asyncio.to_thread(command.upgrade, config, "head")
        await asyncio.to_thread(command.current, config)
        await asyncio.to_thread(command.check, config)
        assert await conn.fetchrow(schema_sql) == before
    finally:
        await conn.execute("DROP SCHEMA IF EXISTS admin CASCADE")
        await conn.execute("DROP OWNED BY bootstrap_migrator_test")
        await conn.execute("DROP ROLE bootstrap_migrator_test")
        await conn.close()
