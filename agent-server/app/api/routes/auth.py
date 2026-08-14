from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Request, Response
from pydantic import BaseModel, Field

from app.api.dependencies import current_session, get_iam_service
from app.config import get_settings
from app.iam.providers import PasswordCredentials
from app.session.factory import get_session_store

router = APIRouter(prefix="/auth", tags=["auth"])


class ExchangeRequest(BaseModel):
    ticket_code: str = Field(min_length=1, max_length=512)


class PasswordLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=1, max_length=32)
    uuid: str = Field(min_length=1, max_length=128)


async def _create_session(response: Response, token, principal) -> dict:
    settings = get_settings()
    session_id, session = await get_session_store().create(token, principal)
    response.set_cookie(
        settings.session_cookie_name,
        session_id,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )
    return {"principal": principal.model_dump(mode="json"), "csrf_token": session.csrf_token}


@router.get("/mode")
async def mode() -> dict[str, str]:
    settings = get_settings()
    return {"mode": settings.ruoyi_auth_mode if settings.iam_mode == "ruoyi" else "ticket"}


@router.post("/exchange")
async def exchange(request: ExchangeRequest, response: Response) -> dict:
    token, principal = await get_iam_service().exchange(request.ticket_code)
    return await _create_session(response, token, principal)


@router.get("/ruoyi/captcha")
async def ruoyi_captcha() -> dict[str, str]:
    challenge = await get_iam_service().captcha()
    image = challenge.image
    if image and not image.startswith("data:image/"):
        image = f"data:image/jpeg;base64,{image}"
    return {"image": image, "uuid": challenge.uuid}


@router.post("/ruoyi/login")
async def ruoyi_login(request: PasswordLoginRequest, response: Response) -> dict:
    token, principal = await get_iam_service().login_password(
        PasswordCredentials(username=request.username, password=request.password, code=request.code, uuid=request.uuid)
    )
    return await _create_session(response, token, principal)


@router.get("/session")
async def session_info(session: tuple = Depends(current_session)) -> dict:
    record, _ = session
    return {"principal": record.principal.model_dump(mode="json"), "csrf_token": record.csrf_token}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    ap_session: str | None = Cookie(default=None, alias="__Host-ap_session"),
) -> dict[str, str]:
    settings = get_settings()
    session_id = ap_session or request.cookies.get(settings.session_cookie_name)
    if session_id:
        await get_session_store().delete(session_id)
    response.delete_cookie(settings.session_cookie_name, path="/")
    return {"status": "ok"}
