import asyncio
import json

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from starlette.requests import Request

from app.database import create_engine, get_connection
from app.repositories.venues import QUALITY_SQL, query_parameters
from tests.conftest import uid


@pytest.mark.integration
async def test_runtime_transactions_are_read_only(database, settings):
    from pydantic import SecretStr
    from starlette.applications import Starlette

    settings.database_url = SecretStr(database[0])
    app = Starlette()
    engine = create_engine(settings)
    app.state.engine = engine
    request = Request({"type": "http", "app": app})
    try:
        async for connection in get_connection(request):
            assert (
                await connection.execute(text("SHOW transaction_read_only"))
            ).scalar_one() == "on"
            assert (
                await connection.execute(text("SHOW transaction_isolation"))
            ).scalar_one() == "repeatable read"
            with pytest.raises(DBAPIError):
                await connection.execute(
                    text("INSERT INTO uranus.organization (uuid,name) VALUES (:id,'must fail')"),
                    {"id": uid(999)},
                )
            await connection.rollback()
    finally:
        await engine.dispose()


@pytest.mark.integration
async def test_quality_query_explain(db_connection, settings, now, tmp_path):
    plan = (
        await db_connection.execute(
            text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + QUALITY_SQL),
            query_parameters(settings, now),
        )
    ).scalar_one()
    assert plan[0]["Plan"]["Actual Rows"] == 2
    # Small-fixture evidence, not a production performance benchmark.
    await asyncio.to_thread(
        (tmp_path / "quality-explain.json").write_text, json.dumps(plan, indent=2)
    )


@pytest.mark.integration
async def test_migrations_only_manage_admin(database, monkeypatch):
    import asyncpg

    url = database[0]
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    fingerprint_sql = """
        SELECT c.oid::text, c.relname, a.attname, a.atttypid::text, a.attnotnull
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0
        WHERE n.nspname='uranus' ORDER BY c.oid, a.attnum
    """
    before = await conn.fetch(fingerprint_sql)
    # A restricted owner can create admin tables but cannot alter Uranus tables.
    await conn.execute("CREATE ROLE admin_migrator_test LOGIN PASSWORD 'fixture-migration-only'")
    await conn.execute("CREATE SCHEMA admin AUTHORIZATION admin_migrator_test")
    migration_url = (
        make_url(url)
        .set(username="admin_migrator_test", password="fixture-migration-only")
        .render_as_string(hide_password=False)
    )
    monkeypatch.setenv("ADMIN_MIGRATION_DATABASE_URL", migration_url)
    config = Config("alembic.ini")
    try:
        await asyncio.to_thread(command.upgrade, config, "head")
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='admin'"
            )
            == 5
        )
        await asyncio.to_thread(command.check, config)
        await asyncio.to_thread(command.downgrade, config, "base")
        assert await conn.fetchval("SELECT to_regclass('admin.finding')") is None
        assert await conn.fetch(fingerprint_sql) == before
        await asyncio.to_thread(command.upgrade, config, "head")
        assert await conn.fetch(fingerprint_sql) == before
    finally:
        await conn.execute("DROP SCHEMA admin CASCADE")
        await conn.execute("DROP ROLE admin_migrator_test")
        await conn.close()
