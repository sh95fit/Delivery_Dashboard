"""P11 Step3-4 사용자 = 이메일 접근규칙 + 계정 + 초대 통합 (도메인 규칙 없음).

- 추가/재초대: 이메일 규칙 upsert + 기존 대기 초대 취소 + 새 초대를 한 트랜잭션으로 처리
- 활성화는 기존 account_service.accept_on_login(첫 구글 로그인)을 그대로 사용
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from sqlalchemy import text

from app.database import get_dash_engine
from app.services import permission_service
from app.services.account_service import _now, _rows, normalize_days, normalize_email


# ── 순수 로직 ──
def user_status(account: dict | None, invite: dict | None, now: datetime) -> tuple[str, int | None]:
    if account and not account.get("active"):
        return "inactive", None
    if account and account.get("activated_at"):
        return "active", None
    if not invite:
        return "none", None
    if invite["status"] == "accepted":
        return "active", None
    if invite["status"] == "revoked":
        return "revoked", None
    if invite["expires_at"] <= now:
        return "expired", None
    left = math.ceil((invite["expires_at"] - now).total_seconds() / 86400)
    return "invited", max(1, left)


def can_deactivate(email: str, is_super: bool, me: str | None) -> bool:
    return not is_super and email.lower() != (me or "").strip().lower()


def can_delete(email: str, is_super: bool, active: bool, me: str | None) -> bool:
    return not active and can_deactivate(email, is_super, me)


def build_rows(rules: list[dict], accounts: list[dict], invites: list[dict],
               now: datetime, me: str | None) -> list[dict]:
    me_n = (me or "").strip().lower()
    acc = {a["email"].lower(): a for a in accounts}
    rule = {r["value"].lower(): r for r in rules}
    inv: dict[str, dict] = {}
    for i in invites:                       # created_at DESC → 이메일별 최신 1건
        inv.setdefault(i["email"].lower(), i)
    out = []
    for e in set(acc) | set(rule) | set(inv):
        a, r, i = acc.get(e), rule.get(e), inv.get(e)
        is_super = bool(a and a.get("is_super"))
        status, days_left = user_status(a, i, now)
        out.append({
            "email": e,
            "permission_set_id": r["permission_set_id"] if r else None,
            "permission_set_name": r["permission_set_name"] if r else None,
            "status": status, "days_left": days_left,
            "is_super": is_super, "is_me": e == me_n,
            "can_deactivate": can_deactivate(e, is_super, me_n),
            "last_login_at": a.get("last_login_at") if a else None,
            "expires_at": i["expires_at"] if i else None,
            "memo": i.get("memo") if i else None,
        })
    out.sort(key=lambda x: (not x["is_super"], x["email"]))
    return out


# ── DB ──
def list_users(me: str) -> list[dict]:
    rules = _rows("""
        SELECT r.value, r.permission_set_id, ps.name AS permission_set_name
        FROM auth_access_rules r
        JOIN auth_permission_sets ps ON ps.id = r.permission_set_id AND ps.deleted_at IS NULL
        WHERE r.kind = 'email' AND r.active AND r.deleted_at IS NULL""")
    accounts = _rows("SELECT email, active, is_super, activated_at, last_login_at "
                     "FROM accounts WHERE deleted_at IS NULL")
    invites = _rows("SELECT email, status, expires_at, memo, created_at "
                    "FROM auth_invitations ORDER BY created_at DESC LIMIT 2000")
    return build_rows(rules, accounts, invites, _now(), me)


def _upsert_rule(c, e: str, ps_id) -> None:
    if ps_id is None:
        raise ValueError("권한셋을 선택하세요")
    if not c.execute(text("SELECT 1 FROM auth_permission_sets WHERE id = :p AND deleted_at IS NULL"),
                     {"p": ps_id}).fetchone():
        raise ValueError("권한셋을 찾을 수 없습니다")
    updated = c.execute(text(
        "UPDATE auth_access_rules SET permission_set_id = :p, active = TRUE "
        "WHERE kind = 'email' AND lower(value) = :e AND deleted_at IS NULL RETURNING id"),
        {"p": ps_id, "e": e}).fetchall()
    if not updated:
        c.execute(text("INSERT INTO auth_access_rules (kind, value, permission_set_id, active) "
                       "VALUES ('email', :e, :p, TRUE)"), {"e": e, "p": ps_id})


def create_user(email: str, ps_id, days, memo: str | None, by: str) -> dict:
    e = normalize_email(email)
    d = normalize_days(days)
    with get_dash_engine().begin() as c:      # 한 트랜잭션 — 중간 실패 시 전부 롤백
        if c.execute(text("SELECT 1 FROM accounts WHERE email = :e AND deleted_at IS NULL "
                          "AND activated_at IS NOT NULL"), {"e": e}).fetchone():
            raise ValueError("이미 가입된 사용자입니다 — 목록에서 권한셋을 바꾸세요")
        _upsert_rule(c, e, ps_id)
        c.execute(text("UPDATE auth_invitations SET status = 'revoked', revoked_by = :b, "
                       "revoked_at = now() WHERE lower(email) = :e AND status = 'pending'"),
                  {"e": e, "b": by})
        c.execute(text("INSERT INTO auth_invitations (email, invited_by, expires_at, memo) "
                       "VALUES (:e, :b, :x, :m)"),
                  {"e": e, "b": by, "x": _now() + timedelta(days=d),
                   "m": (memo or "").strip() or None})
    permission_service.invalidate(e)
    return {"email": e}


def set_permission_set(email: str, ps_id) -> dict:
    e = normalize_email(email)
    with get_dash_engine().begin() as c:
        _upsert_rule(c, e, ps_id)
    permission_service.invalidate(e)
    return {"email": e, "permission_set_id": ps_id}


def set_active(email: str, active: bool, by: str) -> dict:
    e = normalize_email(email)
    found = _rows("SELECT is_super FROM accounts WHERE email = :e AND deleted_at IS NULL", e=e)
    if not found:
        raise ValueError("계정을 찾을 수 없습니다 (아직 로그인 전인 사용자)")
    if not active and not can_deactivate(e, bool(found[0]["is_super"]), by):
        raise ValueError("마스터 계정과 본인 계정은 비활성화할 수 없습니다")
    with get_dash_engine().begin() as c:
        c.execute(text("UPDATE accounts SET active = :a WHERE email = :e"), {"a": active, "e": e})
    permission_service.invalidate(e)
    return {"email": e, "active": active}


def revoke_invite(email: str, by: str) -> dict:
    e = normalize_email(email)
    with get_dash_engine().begin() as c:
        rows = c.execute(text("UPDATE auth_invitations SET status = 'revoked', revoked_by = :b, "
                              "revoked_at = now() WHERE lower(email) = :e AND status = 'pending' "
                              "RETURNING id"), {"e": e, "b": by}).fetchall()
    if not rows:
        raise ValueError("대기 중인 초대가 없습니다")
    return {"email": e}


def delete_user(email: str, by: str) -> dict:
    e = normalize_email(email)
    found = _rows("SELECT is_super, active FROM accounts WHERE email = :e AND deleted_at IS NULL", e=e)
    if not found:
        raise ValueError("계정을 찾을 수 없습니다")
    if not can_delete(e, bool(found[0]["is_super"]), bool(found[0]["active"]), by):
        raise ValueError("비활성 상태인 일반 계정만 삭제할 수 있습니다")
    with get_dash_engine().begin() as c:
        c.execute(text("UPDATE accounts SET deleted_at = now() WHERE email = :e AND deleted_at IS NULL"), {"e": e})
        c.execute(text("UPDATE auth_access_rules SET deleted_at = now(), active = FALSE "
                       "WHERE kind = 'email' AND lower(value) = :e AND deleted_at IS NULL"), {"e": e})
        c.execute(text("UPDATE auth_invitations SET status = 'revoked', revoked_by = :b, revoked_at = now() "
                       "WHERE lower(email) = :e AND status = 'pending'"), {"e": e, "b": by})
    permission_service.invalidate(e)
    return {"email": e}
