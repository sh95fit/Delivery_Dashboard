import os
from fastapi import Request, HTTPException
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config as StarletteConfig
from starlette.responses import RedirectResponse, Response
from sqlalchemy import text
from app.database import get_engine
from app.security import make_session_token, serialize_session, deserialize_session

# --- 구글 OAuth 클라이언트 ---
starlette_config = StarletteConfig(environ={
    "GOOGLE_CLIENT_ID": os.environ.get("GOOGLE_CLIENT_ID", ""),
    "GOOGLE_CLIENT_SECRET": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
})
oauth = OAuth(starlette_config)
oauth.register(
    name="google",
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


def _ensure_allowlist_table():
    engine = get_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS auth_allowlist (
                id SERIAL PRIMARY KEY,
                kind VARCHAR(10) NOT NULL,       -- 'email' | 'domain'
                value VARCHAR(255) NOT NULL,
                added_by VARCHAR(255),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(kind, value)
            )
        """))
        conn.commit()


def is_allowed_email(email: str) -> bool:
    if not email:
        return False
    email = email.strip().lower()
    domain = email.split("@")[-1]
    _ensure_allowlist_table()
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT kind, value FROM auth_allowlist")
        ).fetchall()
    for kind, value in rows:
        value = value.strip().lower()
        if kind == "email" and value == email:
            return True
        if kind == "domain" and value == domain:
            return True
    return False


def is_admin_email(email: str) -> bool:
    admins = [e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()]
    return email in admins


def get_current_email(request: Request) -> str:
    token = request.cookies.get("lunchlab_session")
    if not token:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    email = deserialize_session(token)
    if not email:
        raise HTTPException(status_code=401, detail="세션 만료")
    return email


def set_session_cookie(response: Response, email: str):
    response.set_cookie(
        key="lunchlab_session",
        value=serialize_session(email),
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=60 * 60 * 24 * 7,
    )
