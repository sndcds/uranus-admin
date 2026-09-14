import secrets
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.database import SettingsDep
from app.errors import APIError

bearer = HTTPBearer(auto_error=False)


class AdminPrincipal(BaseModel):
    subject: str


async def get_current_admin(
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> AdminPrincipal:
    if credentials is None:
        raise APIError(401, "authentication_required", "An administrator credential is required.")
    # DEVELOPMENT ONLY. No user identity or global Uranus permission is fabricated.
    if settings.app_env in {"development", "test"} and settings.dev_auth_enabled:
        token = settings.dev_admin_token
        if token is not None and secrets.compare_digest(
            credentials.credentials.encode(), token.get_secret_value().encode()
        ):
            return AdminPrincipal(subject="development-only")
        raise APIError(401, "invalid_credentials", "Invalid administrator credential.")
    # Uranus authenticates identities but has no demonstrated global admin grant.
    # Replace this branch only after the system-admin authorization contract is defined.
    raise APIError(
        503, "admin_auth_unconfigured", "System administrator authentication is not configured."
    )
