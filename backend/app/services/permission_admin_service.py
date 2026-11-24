"""P11 Step3-2 권한셋·접근규칙 관리 (마스터 전용 API의 로직).

- grants: PAGE_KEYS만 허용, 모든 키를 R/C/U/D로 채움, R 없으면 C/U/D 강제 해제
- 규칙: email | domain, 소문자 저장, 같은 (kind,value) 활성 규칙 중복 불가
- 삭제는 모두 soft delete(deleted_at). 규칙이 연결된 권한셋은 삭제 차단
- 변경 후 permission_service.invalidate()로 캐시 즉시 비움
"""
from __future__ import annotations

import json
import re

from sqlalchemy import text

from app.database import get_dash_engine
from app.permissions import PAGE_KEYS
from app.services import permission_service

OPS = ("R", "C", "U", "D")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DOMAIN = re.compile(r"^[^@\s]+\.[^@\s]+$")


# ── 순수 로직 ──
def normalize_grants(raw: dict | None) -> dict:
    raw = raw or {}
    bad = [k for k in raw if k not in PAGE_KEYS]
    if bad:
        raise ValueError(f"알 수 없는 화면 키: {', '.join(bad)}")
    out = {}
    for k in PAGE_KEYS:
        src = raw.get(k) or {}
        r = bool(src.get("R"))
        out[k] = {op: (r and bool(src.get(op))) if op != "R" else r for op in OPS}
    return out


def normalize_name(name: str | None) -> str:
    n = (name or "").strip()
    if not n:
        raise ValueError("권한셋 이름을 입력하세요")
    return n[:50]


def normalize_rule(kind: str | None, value: str | None) -> tuple[str, str]:
    k = (kind or "").strip().lower()
    v = (value or "").strip().lower()
    if k == "email":
        if not _EMAIL.match(v):
            raise ValueError("이메일 형식이 아닙니다")
    elif k == "domain":
        v = v.lstrip("@")
        if not _DOMAIN.match(v):
            raise ValueError("도메인 형식이 아닙니다 (예: lunchlab.me)")
    else:
        raise ValueError("종류는 email 또는 domain 이어야 합니다")
    return k, v


def pick_rule(rules: list[dict], email: str) -> dict | None:
    e = (email or "").strip().lower()
    dom = e.split("@")[-1]
    for kind, val in (("email", e), ("domain", dom)):
        for r in rules:
            if r["kind"] == kind and r["value"].lower() == val:
                return r
    return None


# ── DB ──
def _rows(sql: str, **p) -> list[dict]:
    with get_dash_engine().connect() as c:
        return [dict(r._mapping) for r in c.execute(text(sql), p)]


def _exec(sql: str, **p):
    with get_dash_engine().begin() as c:
        return c.execute(text(sql), p).fetchone()


def _memo(v: str | None) -> str | None:
    return (v or "").strip() or None


def list_sets() -> list[dict]:
    return _rows("""
        SELECT ps.id, ps.name, ps.grants, ps.builtin, ps.memo,
               (SELECT count(*) FROM auth_access_rules r
                 WHERE r.permission_set_id = ps.id AND r.deleted_at IS NULL) AS rule_count
        FROM auth_permission_sets ps WHERE ps.deleted_at IS NULL ORDER BY ps.id""")


def _check_name(name: str, exclude_id: int | None = None) -> None:
    # name UNIQUE — soft delete된 행도 이름을 점유하므로 미리 검사
    hit = _rows("SELECT deleted_at FROM auth_permission_sets "
                "WHERE name = :n AND id <> coalesce(:x, -1)", n=name, x=exclude_id)
    if hit:
        if hit[0]["deleted_at"] is not None:
            raise ValueError("삭제된 권한셋과 이름이 같습니다 — 다른 이름을 쓰세요")
        raise ValueError("이미 있는 권한셋 이름입니다")


def create_set(name: str, grants: dict, memo: str | None, by: str) -> dict:
    n = normalize_name(name)
    _check_name(n)
    row = _exec("INSERT INTO auth_permission_sets (name, grants, memo, created_by) "
                "VALUES (:n, CAST(:g AS jsonb), :m, :b) RETURNING id",
                n=n, g=json.dumps(normalize_grants(grants)), m=_memo(memo), b=by)
    return {"id": row[0]}


def update_set(set_id: int, name: str, grants: dict, memo: str | None, by: str) -> dict:
    n = normalize_name(name)
    _check_name(n, set_id)
    row = _exec("UPDATE auth_permission_sets SET name = :n, grants = CAST(:g AS jsonb), memo = :m "
                "WHERE id = :i AND deleted_at IS NULL RETURNING id",
                i=set_id, n=n, g=json.dumps(normalize_grants(grants)), m=_memo(memo))
    if not row:
        raise ValueError("권한셋을 찾을 수 없습니다")
    permission_service.invalidate()
    return {"id": set_id}


def delete_set(set_id: int, by: str) -> dict:
    found = _rows("SELECT builtin FROM auth_permission_sets "
                  "WHERE id = :i AND deleted_at IS NULL", i=set_id)
    if not found:
        raise ValueError("권한셋을 찾을 수 없습니다")
    if found[0]["builtin"]:
        raise ValueError("기본 제공 권한셋은 삭제할 수 없습니다")
    used = _rows("SELECT count(*) AS n FROM auth_access_rules "
                 "WHERE permission_set_id = :i AND deleted_at IS NULL", i=set_id)[0]["n"]
    if used:
        raise ValueError(f"접근 규칙 {used}개가 사용 중인 권한셋은 삭제할 수 없습니다")
    _exec("UPDATE auth_permission_sets SET deleted_at = now(), deleted_by = :b "
          "WHERE id = :i AND deleted_at IS NULL RETURNING id", i=set_id, b=by)
    permission_service.invalidate()
    return {"id": set_id}


def list_rules() -> list[dict]:
    return _rows("""
        SELECT r.id, r.kind, r.value, r.permission_set_id, ps.name AS permission_set_name,
               r.active, r.memo
        FROM auth_access_rules r
        LEFT JOIN auth_permission_sets ps ON ps.id = r.permission_set_id
        WHERE r.deleted_at IS NULL
        ORDER BY CASE r.kind WHEN 'email' THEN 0 ELSE 1 END, r.value""")


def _check_set(set_id: int) -> None:
    if not _rows("SELECT 1 FROM auth_permission_sets WHERE id = :i AND deleted_at IS NULL", i=set_id):
        raise ValueError("권한셋을 찾을 수 없습니다")


def _check_dup(kind: str, value: str, exclude_id: int | None = None) -> None:
    if _rows("SELECT 1 FROM auth_access_rules WHERE kind = :k AND lower(value) = :v "
             "AND deleted_at IS NULL AND id <> coalesce(:x, -1)", k=kind, v=value, x=exclude_id):
        raise ValueError("이미 등록된 규칙입니다")


def create_rule(kind: str, value: str, set_id: int, active: bool,
                memo: str | None, by: str) -> dict:
    k, v = normalize_rule(kind, value)
    _check_set(set_id)
    _check_dup(k, v)
    row = _exec("INSERT INTO auth_access_rules (kind, value, permission_set_id, active, memo, created_by) "
                "VALUES (:k, :v, :s, :a, :m, :b) RETURNING id",
                k=k, v=v, s=set_id, a=active, m=_memo(memo), b=by)
    permission_service.invalidate()
    return {"id": row[0]}


def update_rule(rule_id: int, kind: str, value: str, set_id: int, active: bool,
                memo: str | None, by: str) -> dict:
    k, v = normalize_rule(kind, value)
    _check_set(set_id)
    _check_dup(k, v, rule_id)
    row = _exec("UPDATE auth_access_rules SET kind = :k, value = :v, permission_set_id = :s, "
                "active = :a, memo = :m, updated_by = :b, updated_at = now() "
                "WHERE id = :i AND deleted_at IS NULL RETURNING id",
                i=rule_id, k=k, v=v, s=set_id, a=active, m=_memo(memo), b=by)
    if not row:
        raise ValueError("규칙을 찾을 수 없습니다")
    permission_service.invalidate()
    return {"id": rule_id}


def delete_rule(rule_id: int, by: str) -> dict:
    row = _exec("UPDATE auth_access_rules SET deleted_at = now(), deleted_by = :b "
                "WHERE id = :i AND deleted_at IS NULL RETURNING id", i=rule_id, b=by)
    if not row:
        raise ValueError("규칙을 찾을 수 없습니다")
    permission_service.invalidate()
    return {"id": rule_id}
