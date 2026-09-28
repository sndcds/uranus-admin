"""Frozen scope-only migration and lossless, guarded downgrade on disposable PostGIS."""

import asyncio
import io
from uuid import uuid4

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import DBAPIError

from app.research.areas import REGIONS


def test_region_migration_offline_only_changes_constraint(monkeypatch):
    monkeypatch.setenv(
        "ADMIN_MIGRATION_DATABASE_URL", "postgresql+asyncpg://unused@localhost/unused_test"
    )
    output = io.StringIO()
    command.upgrade(Config("alembic.ini", output_buffer=output), "0016:0017", sql=True)
    sql = output.getvalue()
    assert "DROP CONSTRAINT research_area_region" in sql
    assert all(region in sql for region in REGIONS)
    assert "CREATE TABLE" not in sql and "DROP TABLE" not in sql
    output = io.StringIO()
    command.downgrade(Config("alembic.ini", output_buffer=output), "0017:0016", sql=True)
    sql = output.getvalue()
    assert sql.index("LOCK TABLE") < sql.index("RAISE EXCEPTION") < sql.index("DROP CONSTRAINT")
    assert "DELETE" not in sql


@pytest.mark.integration
async def test_region_upgrade_downgrade_preserves_rows_and_guards_new_scope(database, monkeypatch):
    monkeypatch.setenv("ADMIN_MIGRATION_DATABASE_URL", database[0])
    connection = await asyncpg.connect(
        database[0].replace("postgresql+asyncpg://", "postgresql://")
    )
    config = Config("alembic.ini")
    assert not await connection.fetchval("SELECT to_regnamespace('admin')")
    identifier = uuid4()
    try:
        await asyncio.to_thread(command.upgrade, config, "0016")
        await connection.execute(
            """
            INSERT INTO admin.research_area
            (id,area_type,country_code,region_code,name,display_name,osm_type,osm_id,
             osm_admin_level,geometry,centroid,source,retrieved_at,created_at,updated_at)
            VALUES ($1,'municipality','DE','DE-SH','Fixture','Fixture','R',101,8,
             ST_Multi(ST_GeomFromText('POLYGON((9 54,10 54,10 55,9 55,9 54))',4326)),
             ST_GeomFromText('POINT(9.5 54.5)',4326),'osm',now(),now(),now())
        """,
            identifier,
        )
        before = await connection.fetchrow(
            "SELECT * FROM admin.research_area WHERE id=$1", identifier
        )
        oid = await connection.fetchval("SELECT 'admin.research_area'::regclass::oid")
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute("UPDATE admin.research_area SET region_code='DE-BY'")
        await asyncio.to_thread(command.upgrade, config, "0017")
        assert await connection.fetchval("SELECT 'admin.research_area'::regclass::oid") == oid
        assert (
            await connection.fetchrow("SELECT * FROM admin.research_area WHERE id=$1", identifier)
            == before
        )
        for region in REGIONS:
            await connection.execute(
                "UPDATE admin.research_area SET country_code=$1,region_code=$2", region[:2], region
            )
        for country, region in [("DE", "DK-81"), ("DK", "DE-BY"), ("DE", "DE-XX"), ("DK", "DK-86")]:
            with pytest.raises(asyncpg.CheckViolationError):
                await connection.execute(
                    "UPDATE admin.research_area SET country_code=$1,region_code=$2", country, region
                )
        for country, region in [("DE", "DE-BY"), ("DK", "DK-81")]:
            await connection.execute(
                "UPDATE admin.research_area SET country_code=$1,region_code=$2", country, region
            )
            with pytest.raises(DBAPIError, match="Cannot downgrade research regions"):
                await asyncio.to_thread(command.downgrade, config, "0016")
            assert (
                await connection.fetchval("SELECT version_num FROM admin.alembic_version") == "0017"
            )
            assert await connection.fetchval("SELECT id FROM admin.research_area") == identifier
        await connection.execute(
            "UPDATE admin.research_area SET country_code='DE',region_code='DE-SH'"
        )
        await asyncio.to_thread(command.downgrade, config, "0016")
        assert (
            await connection.fetchrow("SELECT * FROM admin.research_area WHERE id=$1", identifier)
            == before
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute("UPDATE admin.research_area SET region_code='DE-BE'")
        await asyncio.to_thread(command.upgrade, config, "head")
        await asyncio.to_thread(command.check, config)
    finally:
        await connection.execute("DROP SCHEMA IF EXISTS admin CASCADE")
        await connection.close()
