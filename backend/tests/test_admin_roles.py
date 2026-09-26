"""Exercise the operator SQL and boundary against disposable PostgreSQL roles."""

import asyncio
import re
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.admin_database import assert_admin_boundary, create_admin_engine
from app.errors import APIError

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "grant",
    [
        "GRANT UPDATE ON admin.geocode_candidate TO admin_history_test",
        "GRANT DELETE ON admin.geocode_candidate TO admin_history_test",
        "GRANT DELETE ON admin.geocode_request TO admin_history_test",
        "GRANT TRUNCATE ON admin.geocode_request TO admin_history_test",
        "GRANT CREATE ON SCHEMA admin TO admin_history_test",
        "GRANT UPDATE ON uranus.venue TO admin_history_test",
        "GRANT UPDATE ON admin.record_mark_event TO admin_history_test",
        "GRANT DELETE ON admin.record_mark_event TO admin_history_test",
        "GRANT TRUNCATE ON admin.record_mark_event TO admin_history_test",
        "GRANT TRIGGER ON admin.record_mark_event TO admin_history_test",
        "GRANT UPDATE ON admin.finding_event TO admin_history_test",
        "GRANT DELETE ON admin.finding_event TO admin_history_test",
        "GRANT UPDATE ON admin.assignment_event TO admin_history_test",
        "GRANT DELETE ON admin.assignment_event TO admin_history_test",
    ],
    ids=[
        "candidate-update",
        "candidate-delete",
        "request-delete",
        "request-truncate",
        "admin-ddl",
        "domain-update",
        "history-update",
        "history-delete",
        "truncate",
        "trigger",
        "finding-history-update",
        "finding-history-delete",
        "assignment-history-update",
        "assignment-history-delete",
    ],
)
async def test_boundary_rejects_excessive_runtime_grant(admin_store, db_connection, grant):
    await assert_admin_boundary(admin_store)
    # The fixture rolls back the grant; SET ROLE observes it in the same transaction.
    await db_connection.execute(text(grant))
    await db_connection.execute(text("SET LOCAL ROLE admin_history_test"))
    try:
        with pytest.raises(APIError) as error:
            await assert_admin_boundary(db_connection)
        assert error.value.status == 503
        assert error.value.code == "admin_storage_unconfigured"
        assert error.value.message == "Admin storage requires a restricted role."
    finally:
        await db_connection.execute(text("RESET ROLE"))


async def test_boundary_rejects_history_owner_membership(admin_store, db_connection):
    await assert_admin_boundary(admin_store)
    # Transaction rollback removes the synthetic role and restores ownership/membership.
    await db_connection.execute(text("CREATE ROLE admin_owner_boundary_test NOLOGIN"))
    await db_connection.execute(
        text("ALTER TABLE admin.record_mark_event OWNER TO admin_owner_boundary_test")
    )
    await db_connection.execute(
        text("REVOKE ALL ON admin.record_mark_event FROM admin_owner_boundary_test")
    )
    await db_connection.execute(text("GRANT admin_owner_boundary_test TO admin_history_test"))
    await db_connection.execute(text("SET LOCAL ROLE admin_history_test"))
    try:
        flags = (
            await db_connection.execute(
                text("""
SELECT has_table_privilege(current_user,'admin.record_mark_event','UPDATE'),
       has_table_privilege(current_user,'admin.record_mark_event','DELETE'),
       pg_has_role(current_user,'admin_owner_boundary_test','USAGE')
""")
            )
        ).one()
        # Reject ownership even without currently granted mutation privileges.
        assert flags == (False, False, True)
        with pytest.raises(APIError, match="Admin storage requires a restricted role"):
            await assert_admin_boundary(db_connection)
    finally:
        await db_connection.execute(text("RESET ROLE"))


async def test_documented_provisioning_with_real_logins(database, settings, monkeypatch):
    document = await asyncio.to_thread(
        (Path(__file__).parents[1] / "docs" / "development.md").read_text
    )
    blocks = re.findall(r"```sql\n(-- provisioning: [^\n]+\n.*?)\n```", document, re.DOTALL)
    assert len(blocks) == 2
    url = make_url(database[0])
    conn = await asyncpg.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False)
    )
    # The database fixture requires a disposable *_test database. Never take over
    # existing cluster-global roles or an existing admin schema, even there.
    try:
        assert not await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_roles "
            "WHERE rolname IN ('uranus_reader','admin_user','admin_migrator'))"
        )
        assert not await conn.fetchval("SELECT to_regnamespace('admin')")
    except BaseException:
        await conn.close()
        raise
    engine = None
    try:
        await conn.execute(blocks[0])
        # Synthetic fixed credentials: no SQL interpolation and no environment secrets.
        await conn.execute("ALTER ROLE admin_migrator PASSWORD 'fixture-doc-migration-only'")
        await conn.execute("ALTER ROLE admin_user PASSWORD 'fixture-doc-runtime-only'")
        await conn.execute("ALTER ROLE uranus_reader PASSWORD 'fixture-doc-reader-only'")
        migration_url = url.set(
            username="admin_migrator", password="fixture-doc-migration-only"
        ).render_as_string(hide_password=False)
        monkeypatch.setenv("ADMIN_MIGRATION_DATABASE_URL", migration_url)
        await asyncio.to_thread(command.upgrade, Config("alembic.ini"), "head")
        await conn.execute(blocks[1])

        settings.admin_database_url = SecretStr(
            url.set(username="admin_user", password="fixture-doc-runtime-only").render_as_string(
                hide_password=False
            )
        )
        engine = create_admin_engine(settings)
        assert engine is not None
        async with engine.connect() as runtime:
            await assert_admin_boundary(runtime)
            assert (
                await runtime.execute(
                    text(
                        "SELECT rolsuper,rolcreaterole,rolcreatedb,rolcanlogin "
                        "FROM pg_roles WHERE rolname=current_user"
                    )
                )
            ).one() == (False, False, False, True)
            assert (
                await runtime.execute(
                    text("""
SELECT has_schema_privilege(current_user,'admin','USAGE'),
       has_schema_privilege(current_user,'admin','CREATE'),
       has_schema_privilege(current_user,'uranus','CREATE'),
       pg_has_role(current_user,'admin_migrator','MEMBER'),
       pg_has_role(current_user,'admin_migrator','USAGE'),
       pg_has_role(current_user,'admin_migrator','SET')
""")
                )
            ).one() == (True, False, False, False, False, False)
            expected = {
                "geocode_request": (True, True, True, False, False, False),
                "geocode_candidate": (True, True, False, False, False, False),
                "geo_area": (True, True, True, False, False, False),
                "notification": (True, True, True, False, False, False),
                "notification_delivery": (True, True, True, False, False, False),
                "notification_delivery_item": (True, True, False, False, False, False),
                "url_check": (True, True, True, False, False, False),
                "auth_account": (True, False, False, False, False, False),
                "auth_system_admin": (True, False, False, False, False, False),
                "auth_journalist": (True, False, False, False, False, False),
                "auth_session": (True, True, True, False, False, False),
                "auth_login_bucket": (True, True, True, False, False, False),
                "alembic_version": (True, False, False, False, False, False),
                "check_run": (True, True, True, False, False, False),
                "finding": (True, True, True, False, False, False),
                "finding_event": (True, True, False, False, False, False),
                "assignment": (True, True, True, False, False, False),
                "assignment_event": (True, True, False, False, False, False),
                "record_mark": (True, True, True, False, False, False),
                "record_mark_event": (True, True, False, False, False, False),
            }
            rows = (
                await runtime.execute(
                    text("""
SELECT c.relname, pg_get_userbyid(c.relowner) AS owner,
       has_table_privilege(current_user,c.oid,'SELECT'),
       has_table_privilege(current_user,c.oid,'INSERT'),
       has_table_privilege(current_user,c.oid,'UPDATE'),
       has_table_privilege(current_user,c.oid,'DELETE'),
       has_table_privilege(current_user,c.oid,'TRUNCATE'),
       has_table_privilege(current_user,c.oid,'TRIGGER')
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='admin' AND c.relkind='r'
""")
                )
            ).all()
            assert {row[0]: tuple(row[2:]) for row in rows} == expected
            assert {row[1] for row in rows} == {"admin_migrator"}

        # Verify the dedicated source login can read the fixture's source tables.
        reader = await asyncpg.connect(
            url.set(
                drivername="postgresql",
                username="uranus_reader",
                password="fixture-doc-reader-only",
            ).render_as_string(hide_password=False)
        )
        try:
            assert await reader.fetchval("SELECT count(*) FROM uranus.venue") == 3
            assert not await reader.fetchval("""
SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='uranus' AND c.relkind='r'
AND (NOT has_table_privilege(current_user,c.oid,'SELECT')
     OR has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')))
""")
            with pytest.raises(asyncpg.InsufficientPrivilegeError):
                await reader.execute("UPDATE uranus.venue SET name='Forbidden'")
        finally:
            await reader.close()

        # New tables/sequences must not inherit blanket runtime privileges.
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE admin_migrator")
            await conn.execute("CREATE TABLE admin.future_history (id serial PRIMARY KEY)")
        assert not await conn.fetchval(
            "SELECT has_table_privilege('admin_user','admin.future_history',"
            "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')"
        )
        assert not await conn.fetchval(
            "SELECT has_sequence_privilege('admin_user','admin.future_history_id_seq',"
            "'SELECT,USAGE,UPDATE')"
        )
    finally:
        if engine is not None:
            await engine.dispose()
        # A failed SQL block may leave an aborted transaction; roll it back first.
        await conn.execute("ROLLBACK")
        await conn.execute("DROP SCHEMA IF EXISTS admin CASCADE")
        for role in ("admin_user", "uranus_reader", "admin_migrator"):
            if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)", role):
                # Only the three static role names created above can reach this SQL.
                await conn.execute(f"DROP OWNED BY {role}")
                await conn.execute(f"DROP ROLE {role}")
        await conn.close()
