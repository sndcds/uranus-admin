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
    async with conn.transaction():
        await conn.execute(
            "CREATE ROLE admin_migrator_test LOGIN PASSWORD 'fixture-migration-only'"
        )
        await conn.execute("CREATE SCHEMA admin AUTHORIZATION admin_migrator_test")
    migration_url = (
        make_url(url)
        .set(username="admin_migrator_test", password="fixture-migration-only")
        .render_as_string(hide_password=False)
    )
    monkeypatch.setenv("ADMIN_MIGRATION_DATABASE_URL", migration_url)
    config = Config("alembic.ini")
    try:
        await asyncio.to_thread(command.upgrade, config, "0001")
        await conn.execute(
            "INSERT INTO admin.finding (id,rule,severity,entity_type,entity_id,message,"
            "first_seen_at,last_seen_at) VALUES ('legacy','legacy','warning','venue','key',"
            "'Preserve me',now(),now())"
        )
        await asyncio.to_thread(command.upgrade, config, "0002")
        await conn.execute(
            "UPDATE admin.finding SET status='exception',exception_reason='Accepted',"
            "reviewed_subject='reviewer',comment='Keep comment'"
        )
        await asyncio.to_thread(command.upgrade, config, "0003")
        assert (
            await conn.fetchval(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='admin'"
            )
            == 5
        )
        await asyncio.to_thread(command.upgrade, config, "0004")
        await asyncio.to_thread(command.check, config)
        assert await conn.fetchval("SELECT to_regclass('admin.auth_system_admin')") is not None
        assert await conn.fetch(fingerprint_sql) == before
        await asyncio.to_thread(command.downgrade, config, "0003")
        assert await conn.fetchval("SELECT to_regclass('admin.auth_account')") is None
        assert await conn.fetch(fingerprint_sql) == before
        await conn.execute(
            "INSERT INTO admin.record_mark (id,entity_type,entity_key,entity_name,reasons,"
            "urgency,status,version,created_at,created_by,updated_at) "
            "VALUES ($1,'venue','key','Name','[\"incorrect\"]','normal','open',1,now(),'a',now())",
            uid(900),
        )
        await conn.execute(
            "INSERT INTO admin.record_mark_event (id,mark_id,version,kind,author,created_at,"
            "note,status,reasons,urgency) VALUES ($1,$2,1,'created','a',now(),'Lost on downgrade',"
            "'open','[\"incorrect\"]','normal')",
            uid(901),
            uid(900),
        )
        await asyncio.to_thread(command.downgrade, config, "0002")
        assert await conn.fetchval("SELECT to_regclass('admin.record_mark')") is None
        assert await conn.fetchval("SELECT to_regclass('admin.record_mark_event')") is None
        assert await conn.fetchval("SELECT status FROM admin.finding") == "exception"
        assert await conn.fetch(fingerprint_sql) == before
        await asyncio.to_thread(command.downgrade, config, "0001")
        assert await conn.fetchval("SELECT status FROM admin.finding") == "open"
        assert await conn.fetchval("SELECT comment FROM admin.finding") == "Keep comment"
        columns = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='admin' AND table_name='finding'"
        )
        assert not {"assigned_to", "reviewed_subject", "snoozed_until", "exception_reason"} & {
            row["column_name"] for row in columns
        }
        assert await conn.fetch(fingerprint_sql) == before
        await asyncio.to_thread(command.downgrade, config, "base")
        assert await conn.fetchval("SELECT to_regclass('admin.finding')") is None
        assert await conn.fetch(fingerprint_sql) == before
        await asyncio.to_thread(command.upgrade, config, "head")
        assert await conn.fetch(fingerprint_sql) == before
    finally:
        await conn.execute("DROP SCHEMA admin CASCADE")
        await conn.execute("DROP ROLE admin_migrator_test")
        await conn.close()


async def test_runtime_grants_and_boundary(admin_store, db_connection):
    from app.admin_database import assert_admin_boundary
    from app.errors import APIError

    flags = (
        await admin_store.execute(
            text("SELECT rolsuper, rolcreaterole FROM pg_roles WHERE rolname=current_user")
        )
    ).one()
    assert flags == (False, False)
    assert (await admin_store.execute(text("SELECT count(*) FROM uranus.venue"))).scalar_one() == 3
    await assert_admin_boundary(admin_store)
    await admin_store.rollback()
    for sql in (
        "INSERT INTO uranus.organization (uuid,name) VALUES (gen_random_uuid(),'Forbidden')",
        "UPDATE uranus.venue SET name='Forbidden'",
        "DELETE FROM uranus.venue",
        "CREATE TABLE uranus.forbidden (id integer)",
        "CREATE TABLE admin.forbidden (id integer)",
    ):
        with pytest.raises(DBAPIError):
            async with admin_store.begin():
                await admin_store.execute(text(sql))
    for grant, revoke in (
        (
            "GRANT UPDATE(name) ON uranus.venue TO admin_history_test",
            "REVOKE UPDATE(name) ON uranus.venue FROM admin_history_test",
        ),
        (
            "GRANT CREATE ON SCHEMA uranus TO admin_history_test",
            "REVOKE CREATE ON SCHEMA uranus FROM admin_history_test",
        ),
        (
            "GRANT UPDATE(note) ON admin.record_mark_event TO admin_history_test",
            "REVOKE UPDATE(note) ON admin.record_mark_event FROM admin_history_test",
        ),
    ):
        # Evaluate the changed privileges inside the granting transaction via SET ROLE.
        await db_connection.execute(text(grant))
        await db_connection.execute(text("SET LOCAL ROLE admin_history_test"))
        try:
            with pytest.raises(APIError) as error:
                await assert_admin_boundary(db_connection)
            assert error.value.code == "admin_storage_unconfigured"
        finally:
            await db_connection.execute(text("RESET ROLE"))
            await db_connection.execute(text(revoke))
