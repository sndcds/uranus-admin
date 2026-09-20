"""Shared execution primitive for registered diagnostics and provenance, never user SQL."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.admin_database import assert_admin_boundary
from app.repositories.query import ReadQuery


@asynccontextmanager
async def readonly_connection(
    engine: AsyncEngine, *, admin_boundary: bool = False
) -> AsyncIterator[AsyncConnection]:
    async with asyncio.timeout(8), engine.connect() as connection:
        transaction = await connection.begin()
        try:
            await connection.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            await connection.execute(text("SET LOCAL statement_timeout = '5000ms'"))
            await connection.execute(text("SET LOCAL lock_timeout = '1000ms'"))
            await connection.execute(
                text("SET LOCAL idle_in_transaction_session_timeout = '10000ms'")
            )
            if admin_boundary:
                await assert_admin_boundary(connection)
            yield connection
        finally:
            await transaction.rollback()


async def read_registered_rows(
    engine: AsyncEngine, query: "ReadQuery", *, row_limit: int = 50, admin_boundary: bool = False
) -> tuple[list[dict[str, "Any"]], datetime]:
    """Stream a bounded registered statement under the common transaction guard.

    Only internal registry callers use this primitive. The public APIs never
    construct ReadQuery from client SQL. No commit and no unbounded fetchall.
    """
    if not 1 <= row_limit <= 100:
        raise ValueError("Invalid registered result limit")
    async with readonly_connection(engine, admin_boundary=admin_boundary) as connection:
        observed_at = datetime.now(UTC)
        async with connection.stream(query.statement, query.parameters) as result:
            rows = await result.mappings().fetchmany(row_limit)
            return [dict(row) for row in rows], observed_at
