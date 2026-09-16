from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.auth.credentials import extract_admin_credential
from app.auth.dependencies import get_identity
from app.auth.service import AdminPrincipal, cookie_options, login, require_origin, revoke
from app.database import SettingsDep

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    login: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=1024)


@router.post("/login", response_model=AdminPrincipal)
async def sign_in(
    body: LoginBody, request: Request, response: Response, settings: SettingsDep
) -> AdminPrincipal:
    require_origin(request, settings)
    token, principal = await login(request, settings, body.login, body.password.get_secret_value())
    # Revoke a previous browser session on account switching / reauthentication.
    await revoke(request, request.cookies.get(settings.session_cookie))
    response.set_cookie(value=token, **cookie_options(settings))
    return principal


@router.get("/session", response_model=AdminPrincipal)
async def session(principal: Annotated[AdminPrincipal, Depends(get_identity)]) -> AdminPrincipal:
    return principal


@router.post("/logout")
async def sign_out(request: Request, response: Response, settings: SettingsDep) -> dict[str, str]:
    credential = extract_admin_credential(request, settings)
    if credential is None or credential.source == "cookie":
        require_origin(request, settings)
    if credential is not None and credential.revocable:
        await revoke(request, credential.token)
    response.delete_cookie(**cookie_options(settings))
    return {"status": "ok"}
