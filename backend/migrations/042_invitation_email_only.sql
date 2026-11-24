"""P11 Step3-3 계정·초대 관리.

- 초대 = 마스터가 이메일을 미리 등록 (유효기간 1~30일, 기본 7일)
- 수락 = 그 이메일로 첫 구글 로그인. '유효한 초대(미만료) + 접근 규칙'이 모두 있을 때만
  accounts 생성/갱신 + activated_at 기록 + 초대 accepted 처리
- 같은 이메일 재초대 시 기존 대기 초대는 revoked 처리 후 새로 발급
- 비활성화된 계정은 초대로 되살리지 않음 (계정 탭에서 직접 활성화)
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.database import get_dash_engine
from app.services import permission_service

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_SQL_HAS_RULE = """
    SELECT 1 FROM auth_access_rules r
    JOIN auth_permission_sets ps ON ps.id = r.permission_set_id AND ps.deleted_at IS NULL
    WHERE r.active AND r.deleted_at IS NULL
      AND ((r.kind = 'email'  AND lower(r.value) = :e)
        OR (r.kind = 'domain' AND lower(r.value) = split_part(:e, '@', 2)))
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


# ── 초대 ──
def list_invitations() -> list[dict]:
    rows = _rows("""
        SELECT i.id, i.email, i.status, i.memo, i.invited_by, i.created_at, i.expires_at,
               i.accepted_at, i.revoked_by, i.revoked_at,
               EXISTS (SELECT 1 FROM auth_access_rules r
                        WHERE r.active AND r.deleted_at IS NULL
                          AND ((r.kind = 'email'  AND lower(r.value) = lower(i.email))
                            OR (r.kind = 'domain' AND lower(r.value) = split_part(lower(i.email), '@', 2)))
                      ) AS has_rule
        FROM auth_invitations i ORDER BY i.created_at DESC LIMIT 500""")
    now = _now()
    for r in rows:
        r["state"] = invitation_state(r, now)
    return rows


def create_invitation(email: str, days, memo: str | None, by: str) -> dict:
    e = normalize_email(email)
    d = normalize_days(days)
    if _rows("SELECT 1 FROM accounts WHERE email = :e AND deleted_at IS NULL "
             "AND activated_at IS NOT NULL", e=e):
        raise ValueError("이미 가입된 계정입니다")
    with get_dash_engine().begin() as c:
        c.execute(text("UPDATE auth_invitations SET status = 'revoked', revoked_by = :b, "
                       "revoked_at = now() WHERE lower(email) = :e AND status = 'pending'"),
                  {"e": e, "b": by})
        row = c.execute(text(
            "INSERT INTO auth_invitations (email, invited_by, expires_at, memo) "
            "VALUES (:e, :b, :x, :m) RETURNING id"),
            {"e": e, "b": by, "x": _now() + timedelta(days=d),
             "m": (memo or "").strip() or None}).fetchone()
    has_rule = bool(_rows(_SQL_HAS_RULE, e=e))
    return {"id": row[0], "has_rule": has_rule}


def revoke_invitation(inv_id: int, by: str) -> dict:
    with get_dash_engine().begin() as c:
        row = c.execute(text("UPDATE auth_invitations SET status = 'revoked', revoked_by = :b, "
                             "revoked_at = now() WHERE id = :i AND status = 'pending' RETURNING id"),
                        {"i": inv_id, "b": by}).fetchone()
    if not row:
        raise ValueError("대기 중인 초대를 찾을 수 없습니다")
    return {"id": inv_id}


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


# ── 계정 ──
def list_accounts() -> list[dict]:
    return _rows("""
        SELECT a.id, a.email, a.active, a.is_super, a.activated_at, a.last_login_at,
               a.created_at, a.invitation_id,
               (SELECT ps.name FROM auth_access_rules r
                  JOIN auth_permission_sets ps ON ps.id = r.permission_set_id AND ps.deleted_at IS NULL
                 WHERE r.active AND r.deleted_at IS NULL
                   AND ((r.kind = 'email'  AND lower(r.value) = a.email)
                     OR (r.kind = 'domain' AND lower(r.value) = split_part(a.email, '@', 2)))
                 ORDER BY CASE r.kind WHEN 'email' THEN 0 ELSE 1 END LIMIT 1) AS permission_set_name
        FROM accounts a WHERE a.deleted_at IS NULL
        ORDER BY a.is_super DESC, a.email""")


def set_account_active(acc_id: int, active: bool, by: str) -> dict:
    found = _rows("SELECT email, is_super FROM accounts WHERE id = :i AND deleted_at IS NULL", i=acc_id)
    if not found:
        raise ValueError("계정을 찾을 수 없습니다")
    if not active and found[0]["email"] == (by or "").lower():
        raise ValueError("자기 계정은 비활성화할 수 없습니다")
    if not active and found[0]["is_super"]:
        raise ValueError("시스템 마스터 계정은 비활성화할 수 없습니다")
    with get_dash_engine().begin() as c:
        c.execute(text("UPDATE accounts SET active = :a WHERE id = :i"), {"a": active, "i": acc_id})
    permission_service.invalidate(found[0]["email"])
    return {"id": acc_id, "active": active}
