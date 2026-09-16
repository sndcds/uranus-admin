"""One transport policy for authentication and revocation. Never repr credentials."""

import re
import secrets
from dataclasses import dataclass, field
from typing import Literal

from fastapi import Request

from app.auth.service import invalid
from app.config import Settings


@dataclass(frozen=True)
class AdminCredential:
    source: Literal["cookie", "bearer", "dev"]
    token: str = field(repr=False)

    @property
    def revocable(self) -> bool:
        return self.source != "dev"


def extract_admin_credential(request: Request, settings: Settings) -> AdminCredential | None:
    cookie = request.cookies.get(settings.session_cookie)
    header = request.headers.get("authorization")
    token = cookie
    source: Literal["cookie", "bearer", "dev"] = "cookie"
    if header is not None:
        match = re.fullmatch(r"Bearer ([^\s]{1,8192})", header, re.IGNORECASE)
        if match is None:
            raise invalid()
        token = match[1]
        if cookie is not None and not secrets.compare_digest(cookie.encode(), token.encode()):
            raise invalid()
        # Both equal: preserve cookie CSRF requirements.
        source = "cookie" if cookie is not None else "bearer"
        if settings.app_env in {"development", "test"} and settings.dev_auth_enabled:
            dev = settings.dev_admin_token
            if dev is not None and secrets.compare_digest(
                token.encode(), dev.get_secret_value().encode()
            ):
                return AdminCredential("dev", token)
    if token is None:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise invalid()
    return AdminCredential(source, token)
