"""Independent admin identity, separate authorization and server-side sessions."""

import asyncio
import hashlib
import re
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Request
from pydantic import BaseModel
from sqlalchemy import case, delete, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from starlette.requests import HTTPConnection

from app.admin_database import assert_admin_boundary
from app.admin_tables import (
    auth_account,
    auth_journalist,
    auth_login_bucket,
    auth_session,
    auth_system_admin,
)
from app.config import Settings
from app.errors import APIError

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


class AdminPrincipal(BaseModel):
    subject: str
    system_admin: bool = False
    journalist: bool = False


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def normalize_login(value: str) -> str:
    return value.strip().casefold()


def invalid() -> APIError:
    return APIError(401, "invalid_credentials", "Invalid or expired administrator credential.")


def require_origin(request: Request, settings: Settings) -> None:
    if settings.auth_public_origin is None:
        raise APIError(503, "admin_auth_unconfigured", "Administrator login is not configured.")
    if (
        request.headers.get("origin") != settings.auth_public_origin
        or request.headers.get("x-admin-csrf") != "1"
    ):
        raise APIError(403, "csrf_rejected", "Request origin could not be verified.")


@asynccontextmanager
async def storage(request: HTTPConnection) -> AsyncIterator[AsyncConnection]:
    engine: AsyncEngine | None = getattr(request.app.state, "admin_engine", None)
    if engine is None:
        raise APIError(503, "admin_auth_unconfigured", "Administrator storage is not configured.")
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                await assert_admin_boundary(connection)
            yield connection
    except (SQLAlchemyError, OSError, TimeoutError):
        # Never chain database/driver exceptions into debug logs for auth operations.
        raise APIError(
            503, "auth_storage_unavailable", "Administrator authentication unavailable."
        ) from None


# Fixed hash partitions bound storage even if cleanup is temporarily unavailable.
# Collisions only make throttling more conservative; never bypass a limit.
BUCKET_PARTITIONS = 65536


def bucket_key(kind: str, value: str) -> str:
    return digest(f"{kind}:{int(digest(value), 16) % BUCKET_PARTITIONS}")


async def cleanup_login_buckets(connection: AsyncConnection, batch_size: int = 500) -> int:
    """One bounded batch; caller owns transaction and needs maintenance DELETE grants."""
    if not 1 <= batch_size <= 5000:
        raise ValueError("Batch size must be between 1 and 5000")
    keys = (
        select(auth_login_bucket.c.key)
        .where(auth_login_bucket.c.window_end <= datetime.now(UTC))
        .order_by(auth_login_bucket.c.key)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    result = await connection.execute(
        delete(auth_login_bucket).where(auth_login_bucket.c.key.in_(keys))
    )
    return result.rowcount


async def rate_limit(connection: AsyncConnection, login: str, source: str) -> None:
    now = datetime.now(UTC)
    limited = False
    # Shared across workers. Count unknown accounts as well, before expensive hashing.
    async with connection.begin():
        for key, limit in (
            (bucket_key("source", source), 20),
            (bucket_key("login", normalize_login(login)), 10),
            (digest("global"), 1200),
        ):
            statement = insert(auth_login_bucket).values(
                key=key, window_end=now + timedelta(minutes=5), attempts=1
            )
            expired = auth_login_bucket.c.window_end <= now
            count = (
                await connection.execute(
                    statement.on_conflict_do_update(
                        index_elements=[auth_login_bucket.c.key],
                        set_={
                            "window_end": case(
                                (expired, statement.excluded.window_end),
                                else_=auth_login_bucket.c.window_end,
                            ),
                            "attempts": case(
                                (expired, 1),
                                else_=func.least(auth_login_bucket.c.attempts + 1, limit + 1),
                            ),
                        },
                    ).returning(auth_login_bucket.c.attempts)
                )
            ).scalar_one()
            limited |= count > limit
            if limited:
                break
    if limited:
        raise APIError(429, "login_rate_limited", "Too many login attempts. Try again later.")


def verify_password(encoded: str, password: str) -> bool:
    try:
        return hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


async def login(
    request: Request, settings: Settings, name: str, password: str
) -> tuple[str, AdminPrincipal]:
    async with storage(request) as connection:
        await rate_limit(connection, name, request.client.host if request.client else "unknown")
        async with connection.begin():
            row = (
                (
                    await connection.execute(
                        select(auth_account).where(auth_account.c.login == normalize_login(name))
                    )
                )
                .mappings()
                .one_or_none()
            )
        # Bound concurrent Argon2 memory usage per worker; the limiter is per app lifespan.
        async with request.app.state.password_slots:
            matches = await asyncio.to_thread(
                verify_password, row["password_hash"] if row else DUMMY_HASH, password
            )
        if not matches or row is None or not row["is_active"]:
            raise invalid()
        token = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        async with connection.begin():
            # Recheck after password verification. A concurrent password reset also changes
            # credential_version, so any old session remains invalid at its next use.
            current = (
                (
                    await connection.execute(
                        select(auth_account).where(
                            auth_account.c.id == row["id"],
                            auth_account.c.is_active.is_(True),
                            auth_account.c.credential_version == row["credential_version"],
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if current is None:
                raise invalid()
            await connection.execute(
                insert(auth_session).values(
                    token_hash=digest(token),
                    account_id=row["id"],
                    credential_version=row["credential_version"],
                    created_at=now,
                    last_seen_at=now,
                    expires_at=now + timedelta(seconds=settings.auth_session_seconds),
                )
            )
            granted = (
                await connection.execute(
                    select(exists().where(auth_system_admin.c.account_id == row["id"]))
                )
            ).scalar_one()
            journalist = (
                await connection.execute(
                    select(exists().where(auth_journalist.c.account_id == row["id"]))
                )
            ).scalar_one()
        return token, AdminPrincipal(
            subject=f"admin:{row['id']}", system_admin=granted, journalist=journalist
        )


async def session_identity(
    request: HTTPConnection, settings: Settings, token: str
) -> AdminPrincipal:
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise invalid()
    now = datetime.now(UTC)
    async with storage(request) as connection, connection.begin():
        row = (
            (
                await connection.execute(
                    select(
                        auth_account.c.id,
                        auth_session.c.last_seen_at,
                        exists()
                        .where(auth_system_admin.c.account_id == auth_account.c.id)
                        .label("system_admin"),
                        exists()
                        .where(auth_journalist.c.account_id == auth_account.c.id)
                        .label("journalist"),
                    )
                    .select_from(
                        auth_session.join(
                            auth_account, auth_session.c.account_id == auth_account.c.id
                        )
                    )
                    .where(
                        auth_session.c.token_hash == digest(token),
                        auth_session.c.revoked_at.is_(None),
                        auth_session.c.expires_at > now,
                        auth_session.c.last_seen_at
                        > now - timedelta(seconds=settings.auth_idle_seconds),
                        auth_session.c.credential_version == auth_account.c.credential_version,
                        auth_account.c.is_active.is_(True),
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise invalid()
        cutoff = now - timedelta(seconds=settings.auth_session_heartbeat_seconds)
        if row["last_seen_at"] <= cutoff:
            await connection.execute(
                update(auth_session)
                .where(
                    auth_session.c.token_hash == digest(token),
                    auth_session.c.last_seen_at <= cutoff,
                    auth_session.c.last_seen_at
                    > now - timedelta(seconds=settings.auth_idle_seconds),
                    auth_session.c.revoked_at.is_(None),
                    auth_session.c.expires_at > now,
                )
                .values(last_seen_at=now)
            )
        return AdminPrincipal(
            subject=f"admin:{row['id']}",
            system_admin=row["system_admin"],
            journalist=row["journalist"],
        )


async def revoke(request: Request, token: str | None) -> None:
    if token is None or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        return
    async with storage(request) as connection, connection.begin():
        await connection.execute(
            update(auth_session)
            .where(auth_session.c.token_hash == digest(token))
            .values(revoked_at=datetime.now(UTC))
        )


def cookie_options(settings: Settings) -> dict[str, Any]:
    return {
        "key": settings.session_cookie,
        "httponly": True,
        "secure": settings.app_env not in {"development", "test"},
        "samesite": "strict",
        "path": "/",
    }
