"""P11 Step3-2 권한셋 관리 (마스터 전용 API의 로직).

- grants: PAGE_KEYS만 허용, 모든 키를 R/C/U/D로 채움, R 없으면 C/U/D 강제 해제
- 접근 규칙은 이메일 전용이며 user_service(사용자 탭)에서만 관리 (도메인 규칙 폐지: 043·044)
- 삭제는 soft delete(deleted_at). 삭제되지 않은 접근 규칙(비활성 포함)이 연결된 권한셋은 삭제 차단
- 변경 후 permission_service.invalidate()로 캐시 즉시 비움
"""
from __future__ import annotations

import json

from sqlalchemy import text

from app.database import get_dash_engine
from app.permissions import PAGE_KEYS
from app.services import permission_service

OPS = ("R", "C", "U", "D")


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
        raise ValueError(f"사용자 {used}명이 사용 중인 권한셋은 삭제할 수 없습니다")
    _exec("UPDATE auth_permission_sets SET deleted_at = now(), deleted_by = :b "
          "WHERE id = :i AND deleted_at IS NULL RETURNING id", i=set_id, b=by)
    permission_service.invalidate()
    return {"id": set_id}
