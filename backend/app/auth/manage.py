"""Operator-only account management; no HTTP account/grant mutation endpoints."""

import argparse
import asyncio
import getpass
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection

from app.admin_tables import auth_account, auth_session, auth_system_admin
from app.auth.diagnostics import operator_engine, preflight, safe_error
from app.auth.service import hasher, normalize_login
from app.config import Settings


async def manage_account(
    connection: AsyncConnection,
    action: str,
    login: str,
    password: str | None = None,
    active: bool = False,
    system_admin: bool = False,
) -> str:
    login = normalize_login(login)
    if not login or len(login) > 254:
        raise ValueError("Login must contain 1–254 characters")
    if action in {"create", "password"} and (password is None or not 15 <= len(password) <= 1024):
        raise ValueError("Password must contain 15–1024 characters")
    encoded = await asyncio.to_thread(hasher.hash, password) if password is not None else None
    # The operator's transaction serializes all updates and revokes prior sessions.
    row = (
        (
            await connection.execute(
                select(auth_account).where(auth_account.c.login == login).with_for_update()
            )
        )
        .mappings()
        .one_or_none()
    )
    if action == "create":
        if row is not None:
            raise ValueError("Account already exists")
        identifier = uuid4()
        await connection.execute(
            insert(auth_account).values(
                id=identifier, login=login, password_hash=encoded, is_active=active
            )
        )
    else:
        if row is None:
            raise ValueError("Account does not exist")
        identifier = row["id"]
        values: dict[str, object] = {"credential_version": row["credential_version"] + 1}
        if action == "password":
            values["password_hash"] = encoded
        if action in {"activate", "disable"}:
            values["is_active"] = action == "activate"
        await connection.execute(
            update(auth_account).where(auth_account.c.id == identifier).values(**values)
        )
        await connection.execute(
            update(auth_session)
            .where(auth_session.c.account_id == identifier)
            .values(revoked_at=datetime.now(UTC))
        )
    if action == "grant" or (action == "create" and system_admin):
        existing = (
            await connection.execute(
                select(auth_system_admin.c.account_id).where(
                    auth_system_admin.c.account_id == identifier
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            operator = (await connection.execute(text("SELECT current_user"))).scalar_one()
            await connection.execute(
                insert(auth_system_admin).values(account_id=identifier, granted_by=operator)
            )
    if action == "revoke":
        await connection.execute(
            delete(auth_system_admin).where(auth_system_admin.c.account_id == identifier)
        )
    return str(identifier)


async def run_command(
    settings: Settings,
    action: str,
    login: str | None = None,
    active: bool = False,
    system_admin: bool = False,
) -> None:
    engine = operator_engine(settings)
    try:

        def report(label: str, value: str) -> None:
            print(f"{label:<32}{json.dumps(value, ensure_ascii=True)}")

        if action == "doctor":
            report("Management DSN configured", "OK")
        async with engine.begin() as connection:
            await preflight(connection, report if action == "doctor" else None)
        if action == "doctor":
            return
        password = None
        if action in {"create", "password"}:
            password = getpass.getpass("New password (15–1024 characters): ")
            if password != getpass.getpass("Repeat password: "):
                raise ValueError("Passwords do not match")
        async with engine.begin() as connection:
            identifier = await manage_account(
                connection, action, login or "", password, active, system_admin
            )
        print(f"{action}: admin:{identifier}")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["doctor", "create", "password", "activate", "disable", "grant", "revoke"]
    )
    parser.add_argument("login", nargs="?")
    parser.add_argument("--active", action="store_true", help="Activate a new account explicitly")
    parser.add_argument(
        "--system-admin", action="store_true", help="Grant a new account global access explicitly"
    )
    args = parser.parse_args()
    if args.action != "create" and (args.active or args.system_admin):
        parser.error("Creation flags are only valid with create")
    if (args.action == "doctor") != (args.login is None):
        parser.error("Doctor takes no login; account operations require a login")
    try:
        asyncio.run(
            run_command(Settings(), args.action, args.login, args.active, args.system_admin)
        )
    except Exception as error:
        raise SystemExit(safe_error(error)) from None


if __name__ == "__main__":
    main()
