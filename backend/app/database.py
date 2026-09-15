from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.config import Settings


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(),
        echo=False,
        hide_parameters=True,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_timeout_seconds,
        connect_args={
            "timeout": settings.db_timeout_seconds,
            "command_timeout": settings.db_timeout_seconds,
            "server_settings": {
                "application_name": "kulturbytes-admin-api",
                "timezone": "UTC",
                "statement_timeout": str(settings.db_timeout_seconds * 1000),
                "default_transaction_read_only": "on",
            },
        },
    )


async def get_connection(request: Request) -> AsyncGenerator[AsyncConnection]:
    engine: AsyncEngine = request.app.state.engine
    async with engine.connect() as connection, connection.begin():
        # One consistent snapshot for count/page/summary; never write domain data.
        await connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        yield connection


ConnectionDep = Annotated[AsyncConnection, Depends(get_connection)]
