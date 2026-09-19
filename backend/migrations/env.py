"""Migrations own admin only, including bootstrap of a missing admin schema."""

import asyncio
import os
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.admin_tables import metadata


def include_name(name: str | None, type_: str, parent_names: Any) -> bool:
    if type_ == "schema":
        return name == "admin"
    return bool(parent_names.get("schema_name") == "admin")


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    table = obj if type_ == "table" else getattr(obj, "table", None)
    return getattr(table, "schema", None) == "admin"


def configure(connection: Any = None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=metadata,
        version_table_schema="admin",
        include_schemas=True,
        include_name=include_name,
        include_object=include_object,
        literal_binds=connection is None,
    )
    with context.begin_transaction():
        if context.get_context().opts.get("destination_rev") is not None:
            # Run before Alembic creates admin.alembic_version. The conditional
            # also works in offline SQL and avoids requiring database CREATE for
            # an existing schema. Inspection/autogeneration has no destination.
            context.execute("""
DO $admin_bootstrap$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'admin') THEN
        CREATE SCHEMA admin AUTHORIZATION CURRENT_USER;
        REVOKE ALL PRIVILEGES ON SCHEMA admin FROM PUBLIC;
    END IF;
END;
$admin_bootstrap$;
""")
        context.run_migrations()


async def online(url: str) -> None:
    engine = create_async_engine(url, poolclass=pool.NullPool, hide_parameters=True)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(configure)
    finally:
        await engine.dispose()


url = os.environ.get("ADMIN_MIGRATION_DATABASE_URL")
if not url or not url.startswith("postgresql+asyncpg://"):
    raise RuntimeError(
        "Set ADMIN_MIGRATION_DATABASE_URL explicitly; DATABASE_URL is never used for DDL"
    )
if context.is_offline_mode():
    configure(url=url)
else:
    asyncio.run(online(url))
