"""Read-only operator preflight and allowlisted error categories."""

from collections.abc import Callable
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.config import Settings
from app.storage_preflight import StorageIssue, check_grants, check_schema

OPERATOR_GRANTS = {
    "alembic_version": ("SELECT",),
    "auth_account": ("SELECT", "INSERT", "UPDATE"),
    "auth_system_admin": ("SELECT", "INSERT", "DELETE"),
    "auth_session": ("SELECT", "UPDATE"),
}


def operator_engine(settings: Settings) -> AsyncEngine:
    secret = settings.admin_auth_management_database_url
    if secret is None:
        raise StorageIssue("Set ADMIN_AUTH_MANAGEMENT_DATABASE_URL for the operator process")
    try:
        url = make_url(secret.get_secret_value())
        if url.drivername != "postgresql+asyncpg" or not url.database:
            raise ValueError
    except Exception:
        raise StorageIssue("management DSN invalid") from None
    return create_async_engine(
        url, echo=False, hide_parameters=True, connect_args={"timeout": 10, "command_timeout": 10}
    )


async def operator_boundary(connection: AsyncConnection) -> None:
    unsafe = (
        await connection.execute(
            text("""
SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=current_user
 AND (rolsuper OR rolcreaterole OR rolcreatedb OR rolbypassrls OR rolreplication))
 OR EXISTS(SELECT 1 FROM pg_namespace n WHERE n.nspname IN ('admin','uranus')
 AND has_schema_privilege(current_user,n.oid,'CREATE'))
 OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='admin' AND c.relkind IN ('r','p')
 AND pg_has_role(current_user,c.relowner,'MEMBER'))
 OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname='uranus' AND c.relkind IN ('r','p','v','f')
 AND (has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER')
 OR has_any_column_privilege(current_user,c.oid,'INSERT,UPDATE')))
""")
        )
    ).scalar_one()
    if unsafe:
        raise StorageIssue("unsafe operator role")


async def preflight(
    connection: AsyncConnection, report: Callable[[str, str], None] | None = None
) -> list[tuple[str, str]]:
    checks: list[tuple[str, str]] = []

    def emit(label: str, value: str) -> None:
        checks.append((label, value))
        if report is not None:
            report(label, value)

    identity = (await connection.execute(text("SELECT current_database(), current_user"))).one()
    emit("Database connection", "OK")
    emit("Database", identity[0])
    emit("Role", identity[1])
    await check_schema(connection)
    emit("Admin schema", "OK")
    emit("Migration", "current")
    await operator_boundary(connection)
    emit("Operator boundary", "OK")
    for table, privileges in OPERATOR_GRANTS.items():
        await check_grants(connection, {table: privileges})
        emit(f"{table} privileges", "OK")
    return checks


def safe_error(error: BaseException) -> str:
    if isinstance(error, StorageIssue):
        return (
            "operator privileges incomplete"
            if str(error) == "required privileges incomplete"
            else str(error)
        )
    if isinstance(error, ValidationError):
        return "operator configuration invalid"
    state: Any = getattr(getattr(error, "orig", error), "sqlstate", None)
    if state in {"28P01", "28000"}:
        return "database authentication failed"
    if state == "3D000":
        return "database does not exist"
    if state == "42501":
        return "operator privileges incomplete"
    if state == "23505":
        return "account already exists"
    if state in {"42P01", "3F000"}:
        return "admin schema or required table missing"
    if isinstance(error, (OSError, TimeoutError)) or (
        isinstance(state, str) and state.startswith("08")
    ):
        return "database unreachable"
    # These are fixed messages raised by manage_account, never driver exception text.
    known = {
        "Account already exists": "account already exists",
        "Account does not exist": "unknown account",
        "Login must contain 1–254 characters": "login must contain 1–254 characters",
        "Password must contain 15–1024 characters": "password must contain 15–1024 characters",
        "Passwords do not match": "passwords do not match",
    }
    if type(error) is ValueError and str(error) in known:
        return known[str(error)]
    return "account operation failed; run doctor and check operator configuration"
