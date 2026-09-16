"""Read-only schema/grant checks shared by readiness and operator tooling."""

from functools import lru_cache
from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


class StorageIssue(Exception):
    """Only fixed, non-sensitive diagnostic categories are passed here."""


@lru_cache(maxsize=1)
def migration_head() -> str:
    head = ScriptDirectory(
        str(Path(__file__).resolve().parents[1] / "migrations")
    ).get_current_head()
    if head is None:
        raise RuntimeError("Migration head unavailable")
    return head


async def check_schema(connection: AsyncConnection) -> None:
    if not (await connection.execute(text("SELECT to_regnamespace('admin')"))).scalar_one():
        raise StorageIssue("admin schema missing")
    if not (
        await connection.execute(text("SELECT to_regclass('admin.alembic_version')"))
    ).scalar_one():
        raise StorageIssue("migration incompatible")
    versions = (
        (await connection.execute(text("SELECT version_num FROM admin.alembic_version")))
        .scalars()
        .all()
    )
    if versions != [migration_head()]:
        raise StorageIssue("migration incompatible")


async def check_grants(connection: AsyncConnection, grants: dict[str, tuple[str, ...]]) -> None:
    if not (
        await connection.execute(
            text("SELECT has_schema_privilege(current_user, 'admin', 'USAGE')")
        )
    ).scalar_one():
        raise StorageIssue("required privileges incomplete")
    # has_table_privilege with a comma-separated list means ANY, not ALL. Test each grant.
    for table, privileges in grants.items():
        oid = (
            await connection.execute(
                text("SELECT to_regclass(:table)::oid"), {"table": f"admin.{table}"}
            )
        ).scalar_one()
        if oid is None:
            raise StorageIssue("required admin table missing")
        for privilege in privileges:
            allowed = (
                await connection.execute(
                    text("SELECT has_table_privilege(current_user, CAST(:oid AS oid), :privilege)"),
                    {"oid": oid, "privilege": privilege},
                )
            ).scalar_one()
            if not allowed:
                raise StorageIssue("required privileges incomplete")


RUNTIME_GRANTS = {
    "url_check": ("SELECT", "INSERT", "UPDATE"),
    "alembic_version": ("SELECT",),
    "check_run": ("SELECT", "INSERT", "UPDATE"),
    "finding": ("SELECT", "INSERT", "UPDATE"),
    "record_mark": ("SELECT", "INSERT", "UPDATE"),
    "record_mark_event": ("SELECT", "INSERT"),
    "auth_account": ("SELECT",),
    "auth_system_admin": ("SELECT",),
    "auth_session": ("SELECT", "INSERT", "UPDATE"),
    "auth_login_bucket": ("SELECT", "INSERT", "UPDATE"),
}
