from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text

from app.auth import oauth, set_session_cookie
from app.database import get_dash_engine
from app.services import permission_service

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
    # P11-c: 초대 수락 계정 + 접근 규칙(또는 시스템 마스터)만 로그인 허용
    if not email or not permission_service.can_login(email):
        return JSONResponse(
            status_code=403,
            content={"detail": "초대받은 사용자만 이용할 수 있습니다 — 관리자에게 문의하세요"},
        )
    with get_dash_engine().connect() as conn:
        conn.execute(text("UPDATE accounts SET last_login_at = NOW() WHERE email = :e"), {"e": email})
        conn.commit()
    response = RedirectResponse(url="/")
    set_session_cookie(response, email)
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie("lunchlab_session")
    return response
