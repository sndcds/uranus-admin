"""A separate restricted connection for admin history/reviews; never the domain reader."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.config import Settings
from app.errors import APIError


def create_admin_engine(settings: Settings) -> AsyncEngine | None:
    if settings.admin_database_url is None:
        return None
    return create_async_engine(
        settings.admin_database_url.get_secret_value(),
        hide_parameters=True,
        echo=False,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_timeout_seconds,
        connect_args={
            "timeout": settings.db_timeout_seconds,
            "command_timeout": settings.db_timeout_seconds,
            "server_settings": {
                "timezone": "UTC",
                "statement_timeout": str(settings.db_timeout_seconds * 1000),
                "application_name": "kulturbytes-admin-history",
            },
        },
    )


async def assert_admin_boundary(connection: AsyncConnection) -> None:
    unsafe = (
        await connection.execute(
            text("""
SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=current_user AND (rolsuper OR rolcreaterole))
 OR EXISTS(SELECT 1 FROM pg_namespace n WHERE n.nspname IN ('uranus', 'admin')
 AND has_schema_privilege(current_user, n.oid, 'CREATE'))
 OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='uranus' AND c.relkind IN ('r','p','v','f')
 AND (has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')
      OR has_any_column_privilege(current_user,c.oid,'INSERT,UPDATE')))
 OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='admin' AND c.relname IN
     ('record_mark_event','finding_event','assignment_event','geocode_candidate')
 AND (has_table_privilege(current_user,c.oid,'UPDATE,DELETE,TRUNCATE,TRIGGER')
      OR has_any_column_privilege(current_user,c.oid,'UPDATE')
      OR pg_has_role(current_user,c.relowner,'USAGE')))
 OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='admin' AND c.relname='geocode_request'
 AND (has_table_privilege(current_user,c.oid,'DELETE,TRUNCATE,TRIGGER')
      OR pg_has_role(current_user,c.relowner,'USAGE')))
 OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='admin' AND c.relname IN ('auth_account','auth_system_admin','auth_journalist')
 AND (has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')
      OR has_any_column_privilege(current_user,c.oid,'INSERT,UPDATE')
      OR pg_has_role(current_user,c.relowner,'USAGE')))
""")
        )
    ).scalar_one()
    if unsafe:
        raise APIError(
            503, "admin_storage_unconfigured", "Admin storage requires a restricted role."
        )


@asynccontextmanager
async def connect_admin(request: Request) -> AsyncIterator[AsyncConnection]:
    engine: AsyncEngine | None = request.app.state.admin_engine
    if engine is None:
        raise APIError(
            503, "admin_storage_unconfigured", "Admin history storage is not configured."
        )
    async with engine.connect() as connection:
        async with connection.begin():
            await assert_admin_boundary(connection)
        yield connection


async def get_admin_connection(request: Request) -> AsyncIterator[AsyncConnection]:
    async with connect_admin(request) as connection:
        yield connection


AdminConnectionDep = Annotated[AsyncConnection, Depends(get_admin_connection)]
