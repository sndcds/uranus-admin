"""Explicit bounded auth retention; never invoked by a request."""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.admin_tables import auth_session
from app.auth.service import cleanup_login_buckets
from app.config import Settings
from app.storage_preflight import check_grants, check_schema


async def cleanup_batch(
    connection: AsyncConnection, settings: Settings, batch_size: int = 500
) -> dict[str, int]:
    if not 1 <= batch_size <= 5000:
        raise ValueError("Batch size must be between 1 and 5000")
    now = datetime.now(UTC)
    obsolete = or_(
        auth_session.c.expires_at <= now,
        auth_session.c.last_seen_at <= now - timedelta(seconds=settings.auth_idle_seconds),
        auth_session.c.revoked_at
        <= now - timedelta(seconds=settings.auth_revoked_retention_seconds),
    )
    keys = (
        select(auth_session.c.token_hash)
        .where(obsolete)
        .order_by(auth_session.c.token_hash)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    result = await connection.execute(
        delete(auth_session).where(auth_session.c.token_hash.in_(keys))
    )
    return {
        "sessions": result.rowcount,
        "buckets": await cleanup_login_buckets(connection, batch_size),
    }


async def cleanup(settings: Settings, batch_size: int, max_batches: int) -> dict[str, int]:
    if not 1 <= max_batches <= 1000 or not 1 <= batch_size <= 5000:
        raise ValueError("Cleanup bounds invalid")
    if settings.admin_auth_management_database_url is None:
        raise ValueError("Set ADMIN_AUTH_MANAGEMENT_DATABASE_URL for maintenance")
    engine = create_async_engine(
        settings.admin_auth_management_database_url.get_secret_value(),
        hide_parameters=True,
        echo=False,
        connect_args={"timeout": 10, "command_timeout": 30},
    )
    totals = {"sessions": 0, "buckets": 0}
    try:
        async with engine.begin() as conn:
            await check_schema(conn)
            await check_grants(
                conn,
                {
                    "auth_session": ("SELECT", "UPDATE", "DELETE"),
                    "auth_login_bucket": ("SELECT", "UPDATE", "DELETE"),
                },
            )
        for _ in range(max_batches):
            async with engine.begin() as conn:
                counts = await cleanup_batch(conn, settings, batch_size)
            for key, count in counts.items():
                totals[key] += count
            if not any(counts.values()):
                break
        return totals
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["cleanup"])
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-batches", type=int, default=10)
    args = parser.parse_args()
    try:
        totals = asyncio.run(cleanup(Settings(), args.batch_size, args.max_batches))
    except Exception:
        raise SystemExit(
            "Auth cleanup failed; check maintenance grants, configuration and migrations."
        ) from None
    print(f"Removed sessions: {totals['sessions']}; buckets: {totals['buckets']}")


if __name__ == "__main__":
    main()
