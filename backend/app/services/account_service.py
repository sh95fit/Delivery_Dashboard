"""P11 Step3-3 계정·초대 공통 로직.

- 초대 = 마스터가 이메일을 미리 등록 (유효기간 1~30일, 기본 7일) — 생성·취소는 user_service
- 수락 = 그 이메일로 첫 구글 로그인. '유효한 초대(미만료) + 이메일 접근 규칙'이 모두 있을 때만
  accounts 생성/갱신 + activated_at 기록 + 초대 accepted 처리
- 비활성화된 계정은 초대로 되살리지 않음 (사용자 탭 편집에서 활성화)
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import text

from app.database import get_dash_engine
from app.services import permission_service

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_SQL_HAS_RULE = """
    SELECT 1 FROM auth_access_rules r
    JOIN auth_permission_sets ps ON ps.id = r.permission_set_id AND ps.deleted_at IS NULL
    WHERE r.active AND r.deleted_at IS NULL
      AND r.kind = 'email' AND lower(r.value) = :e
    LIMIT 1"""


# ── 순수 로직 ──
def normalize_email(email: str | None) -> str:
    e = (email or "").strip().lower()
    if not _EMAIL.match(e):
        raise ValueError("이메일 형식이 아닙니다")
    return e


def normalize_days(days) -> int:
    if days is None:
        return 7
    try:
        d = int(days)
    except (TypeError, ValueError):
        raise ValueError("유효기간은 숫자(일)로 입력하세요")
    if not 1 <= d <= 30:
        raise ValueError("유효기간은 1~30일입니다")
    return d


def invitation_state(inv: dict, now: datetime) -> str:
    if inv["status"] in ("accepted", "revoked"):
        return inv["status"]
    return "pending" if inv["expires_at"] > now else "expired"


def decide_activation(account: dict | None, invite: dict | None,
                      has_rule: bool, now: datetime) -> str:
    if account and (account.get("activated_at") or not account.get("active")):
        return "skip"
    if not invite or invitation_state(invite, now) != "pending" or not has_rule:
        return "skip"
    return "activate"


# ── DB 공통 ──
def _rows(sql: str, **p) -> list[dict]:
    with get_dash_engine().connect() as c:
        return [dict(r._mapping) for r in c.execute(text(sql), p)]


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── 로그인 시 활성화 (auth callback에서 호출) ──
def accept_on_login(email: str) -> bool:
    """활성화했으면 True. 오류가 나도 로그인 흐름을 깨지 않고 False(이후 can_login이 차단)."""
    try:
        e = normalize_email(email)
        acc = _rows("SELECT id, active, activated_at FROM accounts "
                    "WHERE email = :e AND deleted_at IS NULL", e=e)
        inv = _rows("SELECT id, status, expires_at, accepted_at FROM auth_invitations "
                    "WHERE lower(email) = :e AND status = 'pending' "
                    "ORDER BY created_at DESC LIMIT 1", e=e)
        account = acc[0] if acc else None
        invite = inv[0] if inv else None
        if decide_activation(account, invite, bool(_rows(_SQL_HAS_RULE, e=e)), _now()) != "activate":
            return False
        with get_dash_engine().begin() as c:
            if account:
                c.execute(text("UPDATE accounts SET activated_at = now(), invitation_id = :i "
                               "WHERE id = :a"), {"i": invite["id"], "a": account["id"]})
            else:
                c.execute(text("INSERT INTO accounts (email, active, invitation_id, activated_at) "
                               "VALUES (:e, TRUE, :i, now())"), {"e": e, "i": invite["id"]})
            c.execute(text("UPDATE auth_invitations SET status = 'accepted', accepted_at = now() "
                           "WHERE id = :i"), {"i": invite["id"]})
        permission_service.invalidate(e)
        return True
    except Exception:
        return False
