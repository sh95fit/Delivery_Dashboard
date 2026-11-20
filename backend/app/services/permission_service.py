"""P11-a 권한 판정 서비스. 계산 로직과 무관 — 판정만 담당.

- is_super: ADMIN_EMAILS(환경변수, 기존 방식 상시 폴백 — 기존 관리자 절대 잠금 없음)
            또는 accounts 테이블의 is_super
- perm_of: 권한셋 grants (60초 캐시 — 권한 변경 반영이 최대 1분 늦을 수 있음, 문서화된 동작)
- 계정·권한셋 테이블이 아직 없어도(마이그레이션 전·실행 실패) 예외를 삼켜 기존 동작 유지
"""
from __future__ import annotations

import os
import time

from sqlalchemy import text

from app.database import get_dash_engine

_CACHE: dict[str, tuple[float, dict | None]] = {}
_TTL = 60.0


def _env_admins() -> list[str]:
    return [e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()]


def is_super(email: str) -> bool:
    email = (email or "").strip().lower()
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
    email = (email or "").strip().lower()
    now = time.monotonic()
    hit = _CACHE.get(email)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    out: dict | None = None
    try:
        with get_dash_engine().connect() as conn:
            r = conn.execute(text("""SELECT ps.grants FROM accounts a
                JOIN auth_permission_sets ps ON ps.id = a.auth_permission_set_id
                WHERE a.email = :e AND a.active AND a.deleted_at IS NULL"""),
                             {"e": email}).fetchone()
            out = r[0] if r else None
    except Exception:
        out = None
    _CACHE[email] = (now, out)
    return out


def invalidate(email: str | None = None) -> None:
    """권한 변경 직후 호출용 (P11-b 계정 관리 화면에서 연결)."""
    if email is None:
        _CACHE.clear()
    else:
        _CACHE.pop(email.strip().lower(), None)
