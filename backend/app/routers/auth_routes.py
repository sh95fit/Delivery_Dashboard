from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from app.auth import oauth, set_session_cookie
from app.database import get_dash_engine
from app.services import account_service, permission_service

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
    # P11 Step3-3: 첫 로그인 = 초대 수락 (유효한 초대 + 접근 규칙이 모두 있을 때만 활성화)
    if email:
        account_service.accept_on_login(email)
    # P11-c: 초대 수락 계정 + 접근 규칙(또는 시스템 마스터)만 로그인 허용
    if not email or not permission_service.can_login(email):
        return RedirectResponse(url="/login?error=not_invited", status_code=302)
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
