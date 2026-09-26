from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.credentials import extract_admin_credential
from app.auth.service import AdminPrincipal as AdminPrincipal
from app.auth.service import require_origin, session_identity
from app.database import SettingsDep
from app.errors import APIError

bearer = HTTPBearer(auto_error=False)


async def get_identity(
    request: Request,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AdminPrincipal:
    credential = extract_admin_credential(request, settings)
    if credential is None:
        raise APIError(401, "authentication_required", "An administrator credential is required.")
    if credential.source == "dev":
        return AdminPrincipal(subject="development-only", system_admin=True)
    if credential.source == "cookie" and request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_origin(request, settings)
    return await session_identity(request, settings, credential.token)


async def get_current_admin(
    principal: Annotated[AdminPrincipal, Depends(get_identity)],
) -> AdminPrincipal:
    if not principal.system_admin:
        raise APIError(403, "admin_access_denied", "System administrator permission is required.")
    return principal


async def get_current_research_user(
    principal: Annotated[AdminPrincipal, Depends(get_identity)],
) -> AdminPrincipal:
    if not (principal.system_admin or principal.journalist):
        raise APIError(403, "research_access_denied", "Research permission is required.")
    return principal
