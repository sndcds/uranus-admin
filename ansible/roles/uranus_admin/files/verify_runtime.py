"""Read-only release verification. Output never includes configuration or driver errors."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.admin_database import assert_admin_boundary, create_admin_engine  # noqa: E402
from app.config import Settings  # noqa: E402
from app.database import create_engine  # noqa: E402
from app.source_schema_verify import verify  # noqa: E402
from app.sql_console.runtime import assert_identity as assert_console_identity  # noqa: E402
from app.storage_preflight import RUNTIME_GRANTS, check_grants, check_schema  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402


async def main():
    pre_upgrade = len(sys.argv) == 3 and sys.argv[2] == "pre-upgrade"
    if any(
        key in os.environ
        for key in (
            "ADMIN_MIGRATION_DATABASE_URL",
            "ADMIN_AUTH_MANAGEMENT_DATABASE_URL",
            "DEV_ADMIN_TOKEN",
        )
    ):
        raise ValueError("Privileged environment present")
    settings = Settings(_env_file=None)
    if (
        settings.app_env != "production"
        or settings.dev_auth_enabled
        or settings.openapi_enabled
        or settings.notifications_delivery_enabled
        or settings.admin_auth_management_database_url is not None
        or settings.dev_admin_token is not None
        or settings.auth_public_origin != sys.argv[1]
    ):
        raise ValueError("Unsafe settings")
    console = None
    if "sql_console_database_url" in Settings.model_fields:
        secret = settings.sql_console_database_url
        if secret is None:
            raise ValueError("Missing dedicated console DSN; no fallback")
        console = create_async_engine(
            secret.get_secret_value(),
            echo=False,
            hide_parameters=True,
            poolclass=NullPool,
            connect_args={
                "timeout": 10,
                "server_settings": {
                    "default_transaction_read_only": "on",
                    "statement_timeout": "10000",
                    "lock_timeout": "2000",
                    "TimeZone": "UTC",
                },
            },
        )
    source, admin = create_engine(settings), create_admin_engine(settings)
    if admin is None:
        raise ValueError("Missing admin engine")
    try:
        if console is not None:
            async with console.connect() as conn, conn.begin():
                await conn.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                identity = (
                    await conn.execute(
                        text("""
                    SELECT current_database(), current_user, current_setting('search_path'),
                    has_database_privilege(current_user,current_database(),'TEMPORARY'),
                    has_database_privilege(current_user,current_database(),'CREATE')
                """)
                    )
                ).one()
                if tuple(identity) != (
                    "oklab",
                    "uranus_console_reader",
                    "pg_catalog, uranus",
                    False,
                    False,
                ):
                    raise ValueError("Wrong console identity or effective boundary")
                raw = await conn.get_raw_connection()
                await assert_console_identity(raw.driver_connection)
        for engine, role in ((source, "uranus_reader"), (admin, "admin_user")):
            async with engine.connect() as conn, conn.begin():
                await conn.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                row = (await conn.execute(text("SELECT current_database(), current_user"))).one()
                if tuple(row) != ("oklab", role):
                    raise ValueError("Wrong identity")
                if role == "admin_user":
                    await assert_admin_boundary(conn)
                    if not pre_upgrade:
                        await check_schema(conn)
                        await check_grants(conn, RUNTIME_GRANTS)
                else:
                    report = await verify(conn, settings)
                    if not report["source_contract"]["compatible"]:
                        raise ValueError("Source contract mismatch")
    finally:
        await source.dispose()
        await admin.dispose()
        if console is not None:
            await console.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        print(
            "Release verification failed: check settings, identities, source contract and grants."
        )
        raise SystemExit(1) from None
    print("Release configuration and read-only database verification passed.")
