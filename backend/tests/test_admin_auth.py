import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import DBAPIError

from app.admin_database import assert_admin_boundary
from app.admin_tables import auth_account, auth_session, auth_system_admin
from app.auth.dependencies import get_current_admin
from app.auth.manage import manage_account
from app.auth.service import AdminPrincipal, digest, hasher
from app.main import create_app
from tests.conftest import uid

ORIGIN = "https://admin.example.test"
CSRF = {"Origin": ORIGIN, "X-Admin-CSRF": "1"}
PASSWORD = "synthetic-correct-password-2026"


@pytest.fixture
async def auth_client(admin_store, database, settings):
    # Provision only synthetic accounts. The API uses the real restricted role.
    from sqlalchemy.ext.asyncio import create_async_engine

    owner = create_async_engine(database[0], hide_parameters=True)
    encoded = await asyncio.to_thread(hasher.hash, PASSWORD)
    async with owner.begin() as conn:
        await conn.execute(
            insert(auth_account),
            [
                {"id": uid(810), "login": "operator", "password_hash": encoded, "is_active": True},
                {"id": uid(811), "login": "ordinary", "password_hash": encoded, "is_active": True},
                {"id": uid(812), "login": "inactive", "password_hash": encoded, "is_active": False},
            ],
        )
        await conn.execute(
            insert(auth_system_admin).values(account_id=uid(810), granted_by="test-operator")
        )
    settings.app_env = "production"
    settings.app_debug = False
    settings.dev_auth_enabled = False
    settings.openapi_enabled = False
    settings.auth_public_origin = ORIGIN
    app = create_app(settings)

    @app.get("/api/v1/auth-probe", dependencies=[])
    async def probe(principal: Annotated[AdminPrincipal, Depends(get_current_admin)]):
        return {"subject": principal.subject}

    try:
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client:
                yield client, owner, settings
    finally:
        await owner.dispose()


async def sign_in(client, name="operator", password=PASSWORD):
    return await client.post(
        "/auth/login", headers=CSRF, json={"login": name, "password": password}
    )


async def test_production_identity_and_separate_authorization(auth_client):
    client, owner, settings = auth_client
    assert (await client.get("/api/v1/auth-probe")).status_code == 401
    response = await sign_in(client)
    assert response.status_code == 200
    assert response.json() == {"subject": f"admin:{uid(810)}", "system_admin": True}
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
    assert "Domain=" not in cookie and "Path=/" in cookie
    token = client.cookies.get(settings.session_cookie)
    assert token not in response.text and PASSWORD not in response.text
    assert (await client.get("/api/v1/auth-probe")).status_code == 200
    async with owner.begin() as conn:
        stored = (await conn.execute(select(auth_session.c.token_hash))).scalar_one()
        assert stored == digest(token) and stored != token
        await conn.execute(
            delete(auth_system_admin).where(auth_system_admin.c.account_id == uid(810))
        )
    denied = await client.get("/api/v1/auth-probe")
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "admin_access_denied"
    assert (await client.get("/auth/session")).json()["system_admin"] is False


@pytest.mark.parametrize(
    "name,password",
    [
        ("missing", PASSWORD),
        ("inactive", PASSWORD),
        ("operator", "wrong"),
        ("operator", "x" * 1024),
    ],
)
async def test_login_denies_unknown_inactive_and_invalid(auth_client, name, password):
    client, _, _ = auth_client
    response = await sign_in(client, name, password)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"
    assert response.headers["www-authenticate"] == "Bearer"
    assert "set-cookie" not in response.headers


async def test_ordinary_and_uranus_organization_identity_never_grant_access(auth_client):
    client, _, _ = auth_client
    assert (await sign_in(client, "ordinary")).status_code == 200
    assert (await client.get("/api/v1/auth-probe")).status_code == 403
    # Existing Uranus fixture users/org memberships have no independent admin account.
    assert (await sign_in(client, str(uid(1)))).status_code == 401
    for credential in [
        "unverified.uranus.jwt",
        "refresh-token",
        "development-only",
        secrets.token_urlsafe(32),
    ]:
        response = await client.get(
            "/api/v1/auth-probe", headers={"Authorization": f"Bearer {credential}"}
        )
        assert response.status_code == 401


@pytest.mark.parametrize(
    "change", ["expired", "idle", "revoked", "disabled", "deleted", "password"]
)
async def test_sessions_deny_expiration_revocation_and_account_changes(auth_client, change):
    client, owner, _ = auth_client
    assert (await sign_in(client)).status_code == 200
    now = datetime.now(UTC)
    async with owner.begin() as conn:
        if change == "expired":
            await conn.execute(
                update(auth_session).values(
                    created_at=now - timedelta(hours=2), expires_at=now - timedelta(seconds=1)
                )
            )
        elif change == "idle":
            await conn.execute(update(auth_session).values(last_seen_at=now - timedelta(hours=1)))
        elif change == "revoked":
            await conn.execute(update(auth_session).values(revoked_at=now))
        elif change == "disabled":
            await conn.execute(update(auth_account).values(is_active=False))
        elif change == "deleted":
            await conn.execute(delete(auth_account).where(auth_account.c.id == uid(810)))
        else:
            await conn.execute(update(auth_account).values(credential_version=2))
    assert (await client.get("/api/v1/auth-probe")).status_code == 401


async def test_logout_and_csrf_boundaries(auth_client):
    client, _, settings = auth_client
    assert (
        await client.post("/auth/login", json={"login": "operator", "password": PASSWORD})
    ).status_code == 403
    assert (await sign_in(client)).status_code == 200
    token = client.cookies.get(settings.session_cookie)
    for headers in [
        {},
        {"Origin": "https://evil.example.test", "X-Admin-CSRF": "1"},
        {"Origin": ORIGIN},
    ]:
        assert (await client.post("/auth/logout", headers=headers)).status_code == 403
        assert (await client.post("/api/v1/check-runs", headers=headers)).status_code == 403
    assert (await client.post("/auth/logout", headers=CSRF)).status_code == 200
    assert client.cookies.get(settings.session_cookie) is None
    assert (
        await client.get("/api/v1/auth-probe", headers={"Authorization": f"Bearer {token}"})
    ).status_code == 401


async def test_login_rate_limit_is_shared_and_has_no_credential_leaks(auth_client, capsys):
    client, _, settings = auth_client
    for _ in range(10):
        assert (await sign_in(client, "operator", "wrong-secret-marker")).status_code == 401
    limited = await sign_in(client)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "login_rate_limited"
    output = capsys.readouterr().err
    assert PASSWORD not in output and "wrong-secret-marker" not in output
    assert settings.dev_admin_token.get_secret_value() not in output


async def test_auth_database_failure_is_sanitized_even_in_debug(auth_client, capsys):
    client, owner, settings = auth_client
    settings.app_env = "test"
    settings.app_debug = True
    from app.logging import configure_logging

    configure_logging("INFO", debug=True)
    async with owner.begin() as conn:
        await conn.execute(text("REVOKE SELECT ON admin.auth_account FROM admin_history_test"))
    response = await sign_in(client)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "auth_storage_unavailable"
    output = capsys.readouterr().err
    assert "traceback" in output
    assert PASSWORD not in response.text + output
    assert "InsufficientPrivilegeError" not in output


async def test_runtime_cannot_create_accounts_or_grant_permissions(admin_store):
    await assert_admin_boundary(admin_store)
    await admin_store.rollback()
    for sql in [
        "UPDATE admin.auth_account SET is_active=true",
        "DELETE FROM admin.auth_system_admin",
        "INSERT INTO admin.auth_system_admin(account_id,granted_by) "
        "VALUES (gen_random_uuid(),'self')",
    ]:
        with pytest.raises(DBAPIError):
            async with admin_store.begin():
                await admin_store.execute(text(sql))


@pytest.mark.parametrize("table", ["auth_account", "auth_system_admin"])
async def test_boundary_rejects_runtime_identity_writes(admin_store, db_connection, table):
    from app.errors import APIError

    await db_connection.execute(text(f"GRANT UPDATE ON admin.{table} TO admin_history_test"))
    await db_connection.execute(text("SET LOCAL ROLE admin_history_test"))
    try:
        with pytest.raises(APIError):
            await assert_admin_boundary(db_connection)
    finally:
        await db_connection.execute(text("RESET ROLE"))


async def test_operator_cli_account_and_grant_lifecycle(auth_client):
    client, owner, _ = auth_client
    async with owner.begin() as conn:
        identifier = await manage_account(conn, "create", "new-account", PASSWORD)
    assert identifier and (await sign_in(client, "new-account")).status_code == 401
    async with owner.begin() as conn:
        await manage_account(conn, "activate", "new-account")
    assert (await sign_in(client, "new-account")).status_code == 200
    assert (await client.get("/api/v1/auth-probe")).status_code == 403
    async with owner.begin() as conn:
        await manage_account(conn, "grant", "new-account")
    assert (await client.get("/api/v1/auth-probe")).status_code == 401
    assert (await sign_in(client, "new-account")).status_code == 200
    assert (await client.get("/api/v1/auth-probe")).status_code == 200
    async with owner.begin() as conn:
        await manage_account(conn, "password", "new-account", PASSWORD + "new")
    assert (await client.get("/api/v1/auth-probe")).status_code == 401
    assert (await sign_in(client, "new-account")).status_code == 401
    assert (await sign_in(client, "new-account", PASSWORD + "new")).status_code == 200
    async with owner.begin() as conn:
        await manage_account(conn, "revoke", "new-account")
    assert (await client.get("/api/v1/auth-probe")).status_code == 401


async def test_login_body_limit_without_content_length(client):
    async def chunks():
        yield b'{"login":"operator","password":"'
        yield b"x" * 9000
        yield b'"}'

    response = await client.post(
        "/auth/login", content=chunks(), headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 413
    assert "x" * 100 not in response.text


@pytest.mark.parametrize("environment", ["development", "test"])
async def test_development_identity_is_explicitly_local(settings, environment):
    settings.app_env = environment
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client:
        response = await client.get(
            "/auth/session",
            headers={"Authorization": f"Bearer {settings.dev_admin_token.get_secret_value()}"},
        )
        assert response.status_code == 200
        assert response.json() == {"subject": "development-only", "system_admin": True}


@pytest.mark.parametrize("environment", ["staging", "production"])
async def test_runtime_guard_rejects_development_identity_even_if_settings_are_mutated(
    settings, environment
):
    settings.app_env = environment
    settings.app_debug = False
    settings.openapi_enabled = False
    app = create_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client:
        response = await client.get(
            "/auth/session",
            headers={"Authorization": f"Bearer {settings.dev_admin_token.get_secret_value()}"},
        )
        assert response.status_code == 401
        assert "development-only" not in response.text


async def test_operator_works_with_only_documented_management_grants(admin_store, db_connection):
    await db_connection.execute(text("CREATE ROLE admin_auth_operator_test NOLOGIN"))
    await db_connection.execute(text("GRANT USAGE ON SCHEMA admin TO admin_auth_operator_test"))
    await db_connection.execute(
        text("GRANT SELECT, INSERT, UPDATE ON admin.auth_account TO admin_auth_operator_test")
    )
    await db_connection.execute(
        text("GRANT SELECT, INSERT, DELETE ON admin.auth_system_admin TO admin_auth_operator_test")
    )
    await db_connection.execute(
        text("GRANT SELECT, UPDATE ON admin.auth_session TO admin_auth_operator_test")
    )
    await db_connection.execute(text("SET LOCAL ROLE admin_auth_operator_test"))
    try:
        await manage_account(
            db_connection, "create", "limited-operator-account", PASSWORD, active=True
        )
        await manage_account(db_connection, "grant", "limited-operator-account")
        assert (
            await db_connection.execute(select(auth_system_admin.c.account_id))
        ).scalar_one() is not None
        await manage_account(db_connection, "revoke", "limited-operator-account")
        assert (
            await db_connection.execute(select(auth_system_admin.c.account_id))
        ).scalar_one_or_none() is None
        await manage_account(db_connection, "disable", "limited-operator-account")
        assert (await db_connection.execute(select(auth_account.c.is_active))).scalar_one() is False
    finally:
        await db_connection.execute(text("RESET ROLE"))


def test_every_administrative_route_uses_the_same_authorization_dependency():
    from fastapi.routing import APIRoute

    from app.config import Settings

    app = create_app(Settings(_env_file=None))
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/"):
            assert any(
                dependency.call is get_current_admin for dependency in route.dependant.dependencies
            ), route.path
