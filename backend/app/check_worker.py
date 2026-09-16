"""Standalone durable check worker; HTTP processes only enqueue jobs."""

import argparse
import asyncio
import logging
from contextlib import suppress

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.admin_database import assert_admin_boundary, create_admin_engine
from app.config import Settings
from app.database import create_engine
from app.services.checks import claim_check, execute_check, fail_job, renew_lease
from app.storage_preflight import RUNTIME_GRANTS, check_grants, check_schema


async def work_once(source: AsyncEngine, admin: AsyncEngine, settings: Settings) -> bool:
    async with admin.connect() as connection:
        async with connection.begin():
            await assert_admin_boundary(connection)
            await check_schema(connection)
            await check_grants(connection, RUNTIME_GRANTS)
        job = await claim_check(connection, settings)
        if job is None:
            return False
        stop = asyncio.Event()

        async def heartbeat() -> None:
            while not stop.is_set():
                try:
                    await asyncio.wait_for(stop.wait(), settings.check_job_lease_seconds / 3)
                except TimeoutError:
                    async with admin.connect() as lease_connection:
                        if not await renew_lease(lease_connection, settings, *job):
                            raise RuntimeError("Worker lease lost") from None

        async def execute() -> None:
            async with source.connect() as reader, reader.begin():
                await reader.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                )
                await execute_check(reader, connection, settings, *job)

        # Both tasks belong to this awaited worker operation. No detached HTTP tasks.
        tasks = [asyncio.create_task(execute()), asyncio.create_task(heartbeat())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            stop.set()
            for task in tasks:
                if not task.done():
                    task.cancel()
            for task in tasks:
                with suppress(asyncio.CancelledError, Exception):
                    await task
            # No-op after success. Marks source-open failures/cancellation as failed too.
            await fail_job(connection, *job)
        return True


async def run(settings: Settings, once: bool = False) -> None:
    source, admin = create_engine(settings), create_admin_engine(settings)
    if admin is None:
        await source.dispose()
        raise RuntimeError("Admin storage required")
    try:
        while True:
            try:
                await work_once(source, admin, settings)
            except Exception as exc:
                logging.getLogger("admin.worker").error(
                    "worker_failed", extra={"error_type": type(exc).__name__}
                )
                if once:
                    raise RuntimeError("Worker failed; check storage and migrations") from None
            if once:
                break
            await asyncio.sleep(settings.check_worker_poll_seconds)
    finally:
        await source.dispose()
        await admin.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        asyncio.run(run(Settings(), args.once))
    except KeyboardInterrupt:
        pass
    except Exception:
        raise SystemExit("Worker unavailable; check storage, grants and migrations.") from None


if __name__ == "__main__":
    main()
