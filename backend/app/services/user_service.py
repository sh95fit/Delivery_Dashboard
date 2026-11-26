"""P11 Step3-4 사용자 = 이메일 접근규칙 + 계정 + 초대 통합 (접근 규칙은 이메일 전용).

- 추가/재초대: 이메일 규칙 upsert + 기존 대기 초대 취소 + 새 초대를 한 트랜잭션으로 처리
- 활성화는 account_service.accept_on_login(첫 구글 로그인)을 그대로 사용
- Step3-5 초대 메일 발송 제한: 같은 이메일에 1분 1회 + 최근 1시간 5회(슬라이딩 윈도우)
  · 최초 초대·재초대·재발송을 모두 센다 (이력: auth_invite_sends, 045)
  · 같은 이메일 요청은 pg_advisory_xact_lock으로 직렬화 → 동시 클릭·멀티 워커에서도 1건만 통과
  · SMTP 시도는 성공·실패 모두 센다. 메일 설정이 없으면 SMTP를 시도하지 않으므로 세지 않는다
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import text

from app.database import get_dash_engine
from app.services import mail_service, permission_service
from app.services.account_service import (
    _SQL_HAS_RULE, _now, _rows, invitation_state, normalize_days, normalize_email,
)

logger = logging.getLogger("users")

COOLDOWN_SEC = 60
WINDOW_SEC = 3600
MAX_PER_WINDOW = 5
_LOCK_NS = 11045          # advisory lock 네임스페이스 (초대 발송 전용)


class InviteRateLimited(HTTPException):
    """429 + Retry-After. HTTPException 하위라 deps.guard가 그대로 통과시킨다."""
    def __init__(self, retry_after: int):
        sec = max(1, int(retry_after))
        super().__init__(
            status_code=429,
            detail=(f"초대 메일은 1분에 1회, 1시간에 {MAX_PER_WINDOW}회까지 보낼 수 있습니다 "
                    f"— {sec}초 후 다시 시도하세요"),
            headers={"Retry-After": str(sec)},
        )
        self.retry_after = sec


# ── 순수 로직 ──
def user_status(account: dict | None, invite: dict | None, now: datetime,
                rule_active: bool = True) -> tuple[str, int | None]:
    if account and not account.get("active"):
        return "inactive", None
    if account and account.get("activated_at"):
        return "active", None
    if invite and invite["status"] == "accepted":
        return ("active" if rule_active else "inactive"), None
    if not invite:
        return "none", None
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


def retry_after(attempts: list[datetime], now: datetime, cooldown: int = COOLDOWN_SEC,
                window: int = WINDOW_SEC, limit: int = MAX_PER_WINDOW) -> int | None:
    """발송 가능하면 None, 아니면 기다릴 초. 슬라이딩 윈도우: limit번째 최근 발송이 윈도우를 벗어날 때까지."""
    recent = sorted((t for t in attempts if t > now - timedelta(seconds=window)), reverse=True)
    waits: list[float] = []
    if recent:
        gap = max(0.0, (now - recent[0]).total_seconds())
        if gap < cooldown:
            waits.append(cooldown - gap)
    if len(recent) >= limit:
        waits.append((recent[limit - 1] + timedelta(seconds=window) - now).total_seconds())
    return math.ceil(max(waits)) if waits else None


def resend_check(account: dict | None, invite: dict | None, has_rule: bool, now: datetime) -> None:
    """재발송 가능 여부 — accept_on_login(decide_activation)이 실제로 활성화할 수 있는 상태만 허용."""
    if account and not account.get("active"):
        raise ValueError("비활성 계정입니다 — 사용자 목록에서 먼저 활성화하세요")
    if account and account.get("activated_at"):
        raise ValueError("이미 가입한 사용자입니다 — 초대 메일이 필요 없습니다")
    if not invite:
        raise ValueError("대기 중인 초대가 없습니다 — 사용자 추가로 새로 초대하세요")
    state = invitation_state(invite, now)
    if state == "revoked":
        raise ValueError("취소된 초대입니다 — 사용자 추가로 다시 초대하세요")
    if state == "accepted":
        raise ValueError("이미 수락된 초대입니다")
    if state == "expired":
        raise ValueError("만료된 초대입니다 — '재초대'로 새 초대를 만드세요")
    if not has_rule:
        raise ValueError("이메일 접근 규칙이 없거나 비활성입니다 — 편집에서 권한셋을 지정하세요")


def mail_ready() -> bool:
    user, pw, _ = mail_service.config()
    return bool(user and pw)


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
        status, days_left = user_status(a, i, now, bool(r.get("active", True)) if r else True)
        if status in ("revoked", "none") and not a:
            continue                        # 취소된 초대는 목록에서 숨김
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
        SELECT r.value, r.active, r.permission_set_id, ps.name AS permission_set_name
        FROM auth_access_rules r
        LEFT JOIN auth_permission_sets ps ON ps.id = r.permission_set_id AND ps.deleted_at IS NULL
        WHERE r.kind = 'email' AND r.deleted_at IS NULL""")
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


def _lock(c, e: str) -> datetime:
    """같은 이메일의 발송 트랜잭션을 직렬화하고, 잠금 획득 후의 DB 시각을 돌려준다."""
    c.execute(text("SELECT pg_advisory_xact_lock(:ns, hashtext(:e))"), {"ns": _LOCK_NS, "e": e})
    return c.execute(text("SELECT clock_timestamp()")).scalar()


def _check_rate(c, e: str, db_now: datetime) -> None:
    rows = c.execute(text("SELECT created_at FROM auth_invite_sends "
                          "WHERE lower(email) = :e AND created_at > :since"),
                     {"e": e, "since": db_now - timedelta(seconds=WINDOW_SEC)}).fetchall()
    wait = retry_after([r[0] for r in rows], db_now)
    if wait:
        raise InviteRateLimited(wait)


def _reserve(c, e: str, inv_id: int, kind: str, by: str) -> int:
    return c.execute(text(
        "INSERT INTO auth_invite_sends (email, invitation_id, kind, requested_by, created_at) "
        "VALUES (:e, :i, :k, :b, clock_timestamp()) RETURNING id"),
        {"e": e, "i": inv_id, "k": kind, "b": by}).scalar()


def create_user(email: str, ps_id, days, memo: str | None, by: str,
                reserve_send: bool = True) -> dict:
    e = normalize_email(email)
    d = normalize_days(days)
    with get_dash_engine().begin() as c:      # 한 트랜잭션 — 중간 실패(제한 포함) 시 전부 롤백
        db_now = _lock(c, e)
        if c.execute(text("SELECT 1 FROM accounts WHERE email = :e AND deleted_at IS NULL "
                          "AND activated_at IS NOT NULL"), {"e": e}).fetchone():
            raise ValueError("이미 가입된 사용자입니다 — 목록에서 권한셋을 바꾸세요")
        if reserve_send:
            _check_rate(c, e, db_now)
        _upsert_rule(c, e, ps_id)
        c.execute(text("UPDATE auth_invitations SET status = 'revoked', revoked_by = :b, "
                       "revoked_at = now() WHERE lower(email) = :e AND status = 'pending'"),
                  {"e": e, "b": by})
        inv_id = c.execute(text("INSERT INTO auth_invitations (email, invited_by, expires_at, memo) "
                                "VALUES (:e, :b, :x, :m) RETURNING id"),
                           {"e": e, "b": by, "x": _now() + timedelta(days=d),
                            "m": (memo or "").strip() or None}).scalar()
        send_id = _reserve(c, e, inv_id, "initial", by) if reserve_send else None
    permission_service.invalidate(e)
    return {"email": e, "days": d, "send_id": send_id}


def prepare_resend(email: str, by: str) -> dict:
    """검증 + 제한 확인 + 발송 슬롯 예약(커밋). SMTP는 트랜잭션 밖(라우터)에서 보낸다."""
    e = normalize_email(email)
    if not mail_ready():
        raise ValueError("메일 설정(GMAIL_USER/GMAIL_APP_PASSWORD)이 없어 보낼 수 없습니다")
    with get_dash_engine().begin() as c:
        db_now = _lock(c, e)
        acc = c.execute(text("SELECT active, activated_at FROM accounts "
                             "WHERE lower(email) = :e AND deleted_at IS NULL"), {"e": e}).mappings().first()
        inv = c.execute(text("SELECT id, status, expires_at FROM auth_invitations "
                             "WHERE lower(email) = :e ORDER BY created_at DESC LIMIT 1"),
                        {"e": e}).mappings().first()
        has_rule = c.execute(text(_SQL_HAS_RULE), {"e": e}).first() is not None
        resend_check(dict(acc) if acc else None, dict(inv) if inv else None, has_rule, db_now)
        _check_rate(c, e, db_now)
        send_id = _reserve(c, e, inv["id"], "resend", by)
    days = max(1, math.ceil((inv["expires_at"] - db_now).total_seconds() / 86400))
    return {"email": e, "days": days, "send_id": send_id}


def finish_send(send_id: int | None, result: dict) -> None:
    """발송 결과 기록 (auth_invite_sends + auth_invitations.sent_at/send_error). 기록 실패가 응답을 깨지 않게."""
    if not send_id:
        return
    ok = bool(result.get("mail_sent"))
    try:
        with get_dash_engine().begin() as c:
            c.execute(text("UPDATE auth_invite_sends SET status = :s, error = :err, "
                           "finished_at = clock_timestamp() WHERE id = :i"),
                      {"s": "sent" if ok else "failed", "err": result.get("mail_error"), "i": send_id})
            c.execute(text("UPDATE auth_invitations i SET "
                           "sent_at = CASE WHEN :ok THEN now() ELSE i.sent_at END, send_error = :err "
                           "FROM auth_invite_sends s WHERE s.id = :i AND i.id = s.invitation_id"),
                      {"ok": ok, "err": result.get("mail_error"), "i": send_id})
    except Exception:  # noqa: BLE001
        logger.exception("초대 발송 결과 기록 실패 (send_id=%s)", send_id)


def set_permission_set(email: str, ps_id) -> dict:
    e = normalize_email(email)
    with get_dash_engine().begin() as c:
        _upsert_rule(c, e, ps_id)
    permission_service.invalidate(e)
    return {"email": e, "permission_set_id": ps_id}


def _acct(e: str) -> dict | None:
    r = _rows("SELECT email, is_super, active FROM accounts "
              "WHERE lower(email) = :e AND deleted_at IS NULL", e=e)
    return r[0] if r else None


def set_active(email: str, active: bool, by: str) -> dict:
    e = normalize_email(email)
    a = _acct(e)
    if a and not active and not can_deactivate(e, bool(a["is_super"]), by):
        raise ValueError("마스터 계정과 본인 계정은 비활성화할 수 없습니다")
    with get_dash_engine().begin() as c:
        if a:
            c.execute(text("UPDATE accounts SET active = :a WHERE lower(email) = :e AND deleted_at IS NULL"),
                      {"a": active, "e": e})
        n = c.execute(text("UPDATE auth_access_rules SET active = :a WHERE kind = 'email' "
                           "AND lower(value) = :e AND deleted_at IS NULL RETURNING id"),
                      {"a": active, "e": e}).fetchall()
        if not a and not n:
            raise ValueError("권한셋이 없는 로그인 전 사용자입니다 — 편집에서 권한셋을 먼저 지정하세요")
    permission_service.invalidate(e)
    return {"email": e, "active": active}


def _close(c, e: str, by: str) -> None:
    c.execute(text("UPDATE auth_invitations SET status = 'revoked', revoked_by = :b, revoked_at = now() "
                   "WHERE lower(email) = :e AND status = 'pending'"), {"e": e, "b": by})
    c.execute(text("UPDATE auth_access_rules SET deleted_at = now(), active = FALSE "
                   "WHERE kind = 'email' AND lower(value) = :e AND deleted_at IS NULL"), {"e": e})


def revoke_invite(email: str, by: str) -> dict:
    """초대취소 = 대기 초대 취소 + 규칙 삭제 → 목록에서 사라짐 (가입 계정은 대상 아님)."""
    e = normalize_email(email)
    if _acct(e):
        raise ValueError("이미 로그인한 사용자입니다 — 사용자 목록에서 비활성화하세요")
    with get_dash_engine().begin() as c:
        _close(c, e, by)
    permission_service.invalidate(e)
    return {"email": e}


def delete_user(email: str, by: str) -> dict:
    """비활성 사용자 완전 삭제 (소프트 삭제, 기록은 남김)."""
    e = normalize_email(email)
    row = next((u for u in list_users(by) if u["email"] == e), None)
    if not row or row["status"] != "inactive" or not row["can_deactivate"]:
        raise ValueError("비활성 상태인 일반 사용자만 삭제할 수 있습니다")
    with get_dash_engine().begin() as c:
        c.execute(text("UPDATE accounts SET deleted_at = now() WHERE lower(email) = :e AND deleted_at IS NULL"),
                  {"e": e})
        _close(c, e, by)
    permission_service.invalidate(e)
    return {"email": e}
