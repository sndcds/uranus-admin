import secrets
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.service import AdminPrincipal as AdminPrincipal
from app.auth.service import invalid, require_origin, session_identity
from app.database import SettingsDep
from app.errors import APIError

bearer = HTTPBearer(auto_error=False)


async def get_identity(
    request: Request,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AdminPrincipal:
    if request.headers.get("authorization"):
        if credentials is None:
            raise invalid()
        if settings.app_env in {"development", "test"} and settings.dev_auth_enabled:
            token = settings.dev_admin_token
            if token is not None and secrets.compare_digest(
                credentials.credentials.encode(), token.get_secret_value().encode()
            ):
                return AdminPrincipal(subject="development-only", system_admin=True)
        return await session_identity(request, settings, credentials.credentials)
    token_value = request.cookies.get(settings.session_cookie)
    if token_value is None:
        raise APIError(401, "authentication_required", "An administrator credential is required.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_origin(request, settings)
    return await session_identity(request, settings, token_value)


async def get_current_admin(
    principal: Annotated[AdminPrincipal, Depends(get_identity)],
) -> AdminPrincipal:
    if not principal.system_admin:
        raise APIError(403, "admin_access_denied", "System administrator permission is required.")
    return principal
