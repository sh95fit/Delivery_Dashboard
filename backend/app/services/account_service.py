"""P11-b 계정·권한셋·초대 관리 서비스. require_super로만 진입 가능 (P11-a 미들웨어 아래 2차).

- 계정 CRUD + 권한셋 배정 → 변경 직후 permission_service.invalidate() (캐시 60초 무시)
- 초대 생성: 1회용 토큰, 유효기간 1일 (P11-c에서 메일 발송 연결)
- 도메인 허용 사용자의 첫 로그인 → '열람' 자동 계정 (허용 목록 1차 게이트는 유지)
"""
from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import text

from app.database import get_dash_engine
from app.services import permission_service
from app.services.manager_service import today

TOKEN_HOURS = 24


def _sets(conn, only_active: bool = True):
    q = ("SELECT id, name, builtin, memo FROM auth_permission_sets "
         "WHERE deleted_at IS NULL" + (" AND builtin" if only_active else ""))
    return [dict(r) for r in conn.execute(text(q + " ORDER BY id")).mappings().fetchall()]


def list_permission_sets() -> dict:
    with get_dash_engine().connect() as conn:
        return {"items": _sets(conn, only_active=False)}


def save_permission_set(name: str, grants: dict, email: str, memo: str | None = None,
                        set_id: int | None = None) -> dict:
    if not name or not isinstance(grants, dict):
        raise ValueError("이름과 권한 구성을 확인하세요")
    with get_dash_engine().begin() as conn:
        if set_id is None:
            sid = conn.execute(text("""INSERT INTO auth_permission_sets (name, grants, memo, created_by)
                VALUES (:n, :g::jsonb, :m, :e) RETURNING id"""),
                {"n": name, "g": __import__("json").dumps(grants, ensure_ascii=False), "m": memo, "e": email}).scalar_one()
        else:
            if conn.execute(text("SELECT builtin FROM auth_permission_sets WHERE id = :i"), {"i": set_id}).scalar():
                raise ValueError("기본 권한셋은 수정할 수 없습니다 — 새로 만들어 주세요")
            conn.execute(text("""UPDATE auth_permission_sets SET name = :n, grants = :g::jsonb, memo = :m
                WHERE id = :i AND deleted_at IS NULL"""),
                {"n": name, "g": __import__("json").dumps(grants, ensure_ascii=False), "m": memo, "i": set_id})
            sid = set_id
        permission_service.invalidate()
    return {"ok": True, "id": sid}


def delete_permission_set(set_id: int, email: str) -> dict:
    with get_dash_engine().begin() as conn:
        if conn.execute(text("SELECT builtin FROM auth_permission_sets WHERE id = :i"), {"i": set_id}).scalar():
            raise ValueError("기본 권한셋은 삭제할 수 없습니다")
        used = conn.execute(text("SELECT COUNT(*) FROM accounts WHERE auth_permission_set_id = :i "
                                 "AND deleted_at IS NULL"), {"i": set_id}).scalar()
        if used:
            raise ValueError(f"이 권한셋을 쓰는 계정이 {used}개 있습니다 — 계정 권한을 먼저 바꾸세요")
        conn.execute(text("UPDATE auth_permission_sets SET deleted_at = NOW(), deleted_by = :e WHERE id = :i"),
                     {"i": set_id, "e": email})
    permission_service.invalidate()
    return {"ok": True}


def list_accounts() -> dict:
    with get_dash_engine().connect() as conn:
        rows = conn.execute(text("""SELECT a.id, a.email, a.name, a.is_super, a.active, a.last_login_at,
            ps.name AS set_name, a.auth_permission_set_id
            FROM accounts a LEFT JOIN auth_permission_sets ps ON ps.id = a.auth_permission_set_id
            WHERE a.deleted_at IS NULL ORDER BY a.email""")).mappings().fetchall()
        return {"items": [dict(r) for r in rows]}


def save_account(email: str, name: str | None, set_id: int | None, is_super: bool,
                 active: bool, email_by: str) -> dict:
    email = (email or "").strip().lower()
    if not email:
        raise ValueError("이메일을 입력하세요")
    with get_dash_engine().begin() as conn:
        if set_id is None and not is_super:
            raise ValueError("권한셋을 지정하세요 (시스템 어드민 제외)")
        conn.execute(text("""
            INSERT INTO accounts (email, name, auth_permission_set_id, is_super, active, created_by)
            VALUES (:e, :n, :s, :sup, :act, :by)
            ON CONFLICT (email) DO UPDATE SET name = :n, auth_permission_set_id = :s,
                is_super = :sup, active = :act, deleted_at = NULL
        """), {"e": email, "n": name, "s": set_id, "sup": bool(is_super), "act": bool(active), "by": email_by})
    permission_service.invalidate(email)
    return {"ok": True}


def create_invitation(email: str, set_id: int, invited_by: str) -> dict:
    email = (email or "").strip().lower()
    with get_dash_engine().begin() as conn:
        if conn.execute(text("SELECT 1 FROM accounts WHERE email = :e AND deleted_at IS NULL"),
                        {"e": email}).scalar():
            raise ValueError("이미 계정이 있는 이메일입니다")
        token = secrets.token_urlsafe(32)
        conn.execute(text("""INSERT INTO invitations (token, email, auth_permission_set_id, invited_by, expires_at)
            VALUES (:t, :e, :s, :by, NOW() + INTERVAL '24 hours')"""),
            {"t": token, "e": email, "s": set_id, "by": invited_by})
        expires = conn.execute(text("SELECT expires_at FROM invitations WHERE token = :t"), {"t": token}).scalar()
    return {"ok": True, "token": token, "email": email, "expires_at": expires.isoformat()}


def list_invitations() -> dict:
    with get_dash_engine().connect() as conn:
        rows = conn.execute(text("""SELECT i.id, i.email, i.token, i.invited_by, i.created_at,
            i.expires_at, i.used_at, i.revoked_at,
            CASE WHEN i.used_at IS NOT NULL THEN '사용'
                 WHEN i.revoked_at IS NOT NULL THEN '취소'
                 WHEN i.expires_at < NOW() THEN '만료'
                 ELSE '대기' END AS status
            FROM invitations i ORDER BY i.id DESC LIMIT 100""")).mappings().fetchall()
        return {"items": [dict(r) for r in rows]}


def revoke_invitation(inv_id: int, email_by: str) -> dict:
    with get_dash_engine().begin() as conn:
        conn.execute(text("UPDATE invitations SET revoked_at = NOW() WHERE id = :i AND used_at IS NULL"),
                     {"i": inv_id})
    return {"ok": True}


def accept_invitation(token: str, google_email: str) -> dict:
    """초대 수락 (P11-c에서 링크 진입 화면과 연결). 토큰 이메일 = 구글 계정 이메일일 때만."""
    token = (token or "").strip()
    google_email = (google_email or "").strip().lower()
    with get_dash_engine().begin() as conn:
        row = conn.execute(text("""SELECT id, email, auth_permission_set_id, expires_at, used_at, revoked_at
            FROM invitations WHERE token = :t"""), {"t": token}).mappings().fetchone()
        if not row:
            raise ValueError("초대를 찾을 수 없습니다")
        if row["used_at"] or row["revoked_at"] or row["expires_at"] < datetime.now(row["expires_at"].tzinfo):
            raise ValueError("사용·만료·취소된 초대입니다 — 새로 초대해 주세요")
        if row["email"] != google_email:
            raise ValueError(f"초대된 이메일({row['email']})과 로그인한 계정이 다릅니다")
        conn.execute(text("""INSERT INTO accounts (email, name, auth_permission_set_id, active, created_by)
            VALUES (:e, :e, :s, TRUE, 'invitation')
            ON CONFLICT (email) DO UPDATE SET auth_permission_set_id = :s, deleted_at = NULL, active = TRUE"""),
            {"e": google_email, "s": row["auth_permission_set_id"]})
        conn.execute(text("UPDATE invitations SET used_at = NOW() WHERE id = :i"), {"i": row["id"]})
    permission_service.invalidate(google_email)
    return {"ok": True}


def auto_account_for_allowed(email: str) -> None:
    """로그인 콜백에서 호출 — 허용 목록 통과자 중 계정 없는 사람은 '열람'으로 자동 생성."""
    with get_dash_engine().begin() as conn:
        if conn.execute(text("SELECT 1 FROM accounts WHERE email = :e"), {"e": email}).scalar():
            return
        conn.execute(text("""INSERT INTO accounts (email, name, auth_permission_set_id, active, created_by)
            SELECT :e, :e, (SELECT id FROM auth_permission_sets WHERE name = '열람'), TRUE, 'auto'
            WHERE EXISTS (SELECT 1 FROM auth_permission_sets WHERE name = '열람')"""), {"e": email})
