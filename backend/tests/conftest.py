import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.main import create_app

DEV_TOKEN = "test-only-credential-with-more-than-32-characters"
FIXTURE_DDL = Path("tests/fixtures/uranus.sql").read_text()


def uid(value: int) -> UUID:
    return UUID(int=value)


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        app_env="test",
        openapi_enabled=True,
        uranus_timestamp_timezone="UTC",
        dev_auth_enabled=True,
        dev_admin_token=SecretStr(DEV_TOKEN),
    )


@pytest.fixture
def headers():
    return {"Authorization": f"Bearer {DEV_TOKEN}"}


@pytest.fixture
async def client(settings):
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            yield client


@pytest.fixture(scope="session")
async def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        if os.environ.get("CI"):
            pytest.fail("CI requires TEST_DATABASE_URL; integration tests must not be skipped")
        pytest.skip("Set TEST_DATABASE_URL to an empty disposable database ending in _test")
    parsed = make_url(url)
    if not parsed.database or not parsed.database.endswith("_test"):
        pytest.fail("Refusing fixture DDL outside a database ending in _test")
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    if await conn.fetchval("SELECT to_regnamespace('uranus') IS NOT NULL"):
        await conn.close()
        pytest.fail("Test database must be empty; refusing to replace an existing Uranus schema")
    now = datetime.now(UTC)
    try:
        # One transaction; rollback removes fixtures and schema on setup failure too.
        async with conn.transaction():
            await conn.execute(FIXTURE_DDL)
            stamp = now.replace(tzinfo=None) - timedelta(minutes=1)
            await conn.execute(
                'INSERT INTO uranus."user" '
                "(uuid, created_at, email, password_hash) VALUES ($1,$2,$3,$4)",
                uid(1),
                stamp,
                "fixture@example.invalid",
                "not-a-password-hash",
            )
            for i in (10, 11):
                await conn.execute(
                    "INSERT INTO uranus.organization (uuid,name,created_at) VALUES ($1,$2,$3)",
                    uid(i),
                    f"Organization {i}",
                    stamp,
                )
            for i, org, point in [
                (20, 10, None),
                (21, 10, "POINT(9.4 54.8)"),
                (22, 11, "POINT EMPTY"),
            ]:
                await conn.execute(
                    "INSERT INTO uranus.venue "
                    "(uuid,org_uuid,name,scope,point,created_at,street,house_number,"
                    "postal_code,city,country) VALUES "
                    "($1,$2,$3,'organization',ST_GeomFromText($4,4326),$5,"
                    "'Hafenstraße','3','24937','Flensburg','DEU')",
                    uid(i),
                    uid(org),
                    f"Venue {i}",
                    point,
                    stamp,
                )
            await conn.execute(
                "INSERT INTO uranus.space (uuid,venue_uuid,name,created_at) "
                "VALUES ($1,$2,'Saal',$3)",
                uid(25),
                uid(20),
                stamp,
            )
            for i, org, venue, status in [
                (30, 10, 20, "released"),
                (31, 11, 22, "draft"),
                (32, 10, 21, "released"),
            ]:
                await conn.execute(
                    "INSERT INTO uranus.event "
                    "(uuid,org_uuid,venue_uuid,title,release_status,created_at) "
                    "VALUES ($1,$2,$3,$4,$5,$6)",
                    uid(i),
                    uid(org),
                    uid(venue),
                    f"Event {i}",
                    status,
                    stamp - timedelta(days=30),
                )
            # UTC/date separation is explicit: dates use the configured event timezone.
            from zoneinfo import ZoneInfo

            today = now.astimezone(ZoneInfo("Europe/Berlin")).date()
            dates = [
                (40, 30, None, 1, "inherited"),  # inherited venue20; released
                (41, 30, None, -1, "inherited"),  # past, not counted
                (42, 30, 21, 2, "inherited"),  # override to valid point, not venue20
                (43, 32, 20, 3, "inherited"),  # override from venue21 to venue20
                (44, 31, None, 4, "inherited"),  # draft venue22
                (45, 30, None, 2, "cancelled"),  # count upcoming, not published relevance
                (46, 30, None, 2, "draft"),  # date override suppresses relevance
                (47, 31, None, 2, "released"),  # released date cannot publish draft parent
                (48, 30, None, 30, "inherited"),  # published but outside 14 days
                (49, 30, None, 14, "inherited"),  # exclusive 14-day boundary
            ]
            for i, event, venue, days, status in dates:
                await conn.execute(
                    "INSERT INTO uranus.event_date "
                    "(uuid,event_uuid,venue_uuid,start_date,release_status,created_at) "
                    "VALUES ($1,$2,$3,$4,$5,$6)",
                    uid(i),
                    uid(event),
                    uid(venue) if venue else None,
                    today + timedelta(days=days),
                    status,
                    stamp,
                )
            await conn.execute(
                "INSERT INTO uranus.organization_member_link "
                "(org_uuid,user_uuid,created_at,has_joined) VALUES ($1,$2,$3,false)",
                uid(10),
                uid(1),
                stamp,
            )
            await conn.execute(
                "INSERT INTO uranus.organization_partner_request "
                "(from_org_uuid,to_org_uuid,from_user_uuid,created_at) "
                "VALUES ($1,$2,$3,$4)",
                uid(10),
                uid(11),
                uid(1),
                stamp,
            )
            await conn.execute(
                "INSERT INTO uranus.pluto_image (uuid,file_name,created_at) "
                "VALUES ($1,'fixture.jpg',$2),($3,'unknown.jpg',NULL)",
                uid(60),
                stamp,
                uid(61),
            )
        yield url, now
    finally:
        # This schema was created by this fixture after the empty-database guard.
        await conn.execute("DROP SCHEMA IF EXISTS uranus CASCADE")
        await conn.close()


@pytest.fixture
async def db_connection(database):
    engine = create_async_engine(database[0], poolclass=NullPool)
    try:
        async with engine.connect() as conn, conn.begin():
            yield conn
            await conn.rollback()
    finally:
        await engine.dispose()


@pytest.fixture
async def db_client(database, settings):
    settings.database_url = SecretStr(database[0])
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
        ) as client:
            yield client


@pytest.fixture
def now(database):
    return database[1]


@pytest.fixture
async def admin_store(database, settings):
    from sqlalchemy import text

    from app.admin_database import create_admin_engine
    from app.admin_tables import metadata
    from app.storage_preflight import migration_head

    setup = create_async_engine(database[0], poolclass=NullPool)
    async with setup.begin() as connection:
        assert (
            await connection.execute(text("SELECT to_regnamespace('admin')"))
        ).scalar_one() is None
        await connection.execute(text("CREATE SCHEMA admin"))
        await connection.run_sync(metadata.create_all)
        await connection.execute(
            text("CREATE TABLE admin.alembic_version(version_num varchar(32) PRIMARY KEY)")
        )
        await connection.execute(
            text("INSERT INTO admin.alembic_version VALUES (:head)"), {"head": migration_head()}
        )
        await connection.execute(
            text("CREATE ROLE admin_history_test LOGIN PASSWORD 'fixture-history-only'")
        )
        await connection.execute(text("GRANT USAGE ON SCHEMA admin TO admin_history_test"))
        await connection.execute(
            text("GRANT SELECT ON admin.alembic_version TO admin_history_test")
        )
        await connection.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE ON admin.check_run, admin.finding, "
                "admin.record_mark, admin.url_check, admin.notification, "
                "admin.notification_delivery TO admin_history_test"
            )
        )
        await connection.execute(
            text(
                "GRANT SELECT, INSERT ON admin.record_mark_event, "
                "admin.notification_delivery_item TO admin_history_test"
            )
        )
        await connection.execute(
            text(
                "GRANT SELECT ON admin.auth_account, admin.auth_system_admin TO admin_history_test"
            )
        )
        await connection.execute(
            text(
                "GRANT SELECT, INSERT, UPDATE ON admin.auth_session, "
                "admin.auth_login_bucket TO admin_history_test"
            )
        )
        await connection.execute(text("GRANT USAGE ON SCHEMA uranus TO admin_history_test"))
        await connection.execute(
            text("GRANT SELECT ON ALL TABLES IN SCHEMA uranus TO admin_history_test")
        )
    engine = None
    try:
        settings.admin_database_url = SecretStr(
            make_url(database[0])
            .set(username="admin_history_test", password="fixture-history-only")
            .render_as_string(hide_password=False)
        )
        engine = create_admin_engine(settings)
        async with engine.connect() as connection:
            yield connection
    finally:
        if engine is not None:
            await engine.dispose()
        async with setup.begin() as connection:
            await connection.run_sync(metadata.drop_all)
            await connection.execute(text("DROP TABLE admin.alembic_version"))
            await connection.execute(text("DROP SCHEMA admin"))
            await connection.execute(
                text("REVOKE SELECT ON ALL TABLES IN SCHEMA uranus FROM admin_history_test")
            )
            await connection.execute(text("REVOKE USAGE ON SCHEMA uranus FROM admin_history_test"))
            await connection.execute(text("DROP ROLE admin_history_test"))
        await setup.dispose()
