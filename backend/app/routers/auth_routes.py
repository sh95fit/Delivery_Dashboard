from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.auth import is_allowed_email, oauth, set_session_cookie

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request):
    redirect_uri = "https://dashboard.lunchlab.me/api/auth/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def auth_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}
    email = (userinfo.get("email") or "").lower()
    if not is_allowed_email(email):
        return JSONResponse(
            status_code=403,
            content={"detail": "접근 권한이 없습니다 — 관리자에게 문의하세요"},
        )
    response = RedirectResponse(url="/")
    set_session_cookie(response, email)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("lunchlab_session")
    return response
