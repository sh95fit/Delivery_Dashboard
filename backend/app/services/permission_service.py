"""P11-c 권한 판정 서비스 — 판정만 담당 (계산 로직과 무관).

판정 순서
1) is_super: accounts.is_super (DB) — ADMIN_EMAILS(환경변수)는 비상용 폴백
2) perm_of: 활성 계정 + 초대 수락(activated_at) + 접근 규칙(이메일 > 도메인) → 권한셋 grants
3) can_login: 마스터이거나 perm_of가 있는 사용자만 로그인 허용
- 60초 캐시 (권한 변경 시 invalidate 호출로 즉시 반영)
- 테이블 오류 시 예외를 삼키고 '차단'(안전한 기본값)
"""
from __future__ import annotations

import os
import time

from sqlalchemy import text

from app.database import get_dash_engine

_CACHE: dict[str, tuple[float, dict | None]] = {}
_TTL = 60.0

_SQL_PERM = text("""
    SELECT ps.grants
    FROM accounts a
    JOIN auth_access_rules r
      ON r.active AND r.deleted_at IS NULL
     AND ((r.kind = 'email'  AND lower(r.value) = a.email)
       OR (r.kind = 'domain' AND lower(r.value) = split_part(a.email, '@', 2)))
    JOIN auth_permission_sets ps
      ON ps.id = r.permission_set_id AND ps.deleted_at IS NULL
    WHERE a.email = :e
      AND a.active AND a.deleted_at IS NULL
      AND a.activated_at IS NOT NULL
    ORDER BY CASE r.kind WHEN 'email' THEN 0 ELSE 1 END
    LIMIT 1
""")


def _norm(email: str | None) -> str:
    return (email or "").strip().lower()


def _env_admins() -> list[str]:
    return [e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()]


def is_super(email: str) -> bool:
    email = _norm(email)
    if not email:
        return False
    if email in _env_admins():
        return True
    try:
        with get_dash_engine().connect() as conn:
            r = conn.execute(text("SELECT is_super FROM accounts "
                                  "WHERE email = :e AND active AND deleted_at IS NULL"),
                             {"e": email}).fetchone()
        return bool(r and r[0])
    except Exception:
        return False


def perm_of(email: str) -> dict | None:
    email = _norm(email)
    if not email:
        return None
    now = time.monotonic()
    hit = _CACHE.get(email)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    try:
        with get_dash_engine().connect() as conn:
            r = conn.execute(_SQL_PERM, {"e": email}).fetchone()
        out = r[0] if r else None
    except Exception:
        out = None
    _CACHE[email] = (now, out)
    return out


def can_login(email: str) -> bool:
    return is_super(email) or perm_of(email) is not None


def invalidate(email: str | None = None) -> None:
    if email is None:
        _CACHE.clear()
    else:
        _CACHE.pop(_norm(email), None)
