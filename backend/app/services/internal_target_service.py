"""S0-P3.1 직원식 대상 (dash_db.internal_targets).

지정 대상은 배송 일감·식수에 그대로 포함되고, 매출에서만 빠져 '직원식'으로 따로 표시된다.
조회 시점에 계산하므로 과거 날짜를 포함한 모든 날짜에 적용된다.
"""
from __future__ import annotations

import logging
import threading
import time

from sqlalchemy import bindparam, text

from app.database import get_dash_engine, get_engine

logger = logging.getLogger("internal_targets")

KINDS = ("address", "account")
KIND_LABEL = {"address": "배송지", "account": "고객사"}
CACHE_TTL_SEC = 30

_cache: dict = {"at": 0.0, "value": None}
_lock = threading.Lock()

SQL_ADDR_NAMES = """
SELECT a.id, a.name, a.account_id, acc.name AS account_name
FROM addresses a
LEFT JOIN accounts acc ON acc.id = a.account_id
WHERE a.id IN :ids
"""
SQL_ACC_NAMES = "SELECT acc.id, acc.name FROM accounts acc WHERE acc.id IN :ids"

SQL_SEARCH_ADDR = """
SELECT a.id, a.name, a.account_id, acc.name AS account_name
FROM addresses a
LEFT JOIN accounts acc ON acc.id = a.account_id
WHERE a.name LIKE :q OR acc.name LIKE :q OR a.id = :id
ORDER BY a.id
LIMIT 30
"""
SQL_SEARCH_ACC = """
SELECT acc.id, acc.name, COUNT(a.id) AS address_count
FROM accounts acc
LEFT JOIN addresses a ON a.account_id = acc.id
WHERE acc.name LIKE :q OR acc.id = :id
GROUP BY acc.id, acc.name
ORDER BY acc.id
LIMIT 30
"""


def _empty() -> dict:
    return {"address_ids": set(), "account_ids": set()}


def _copy(v: dict) -> dict:
    return {k: set(s) for k, s in v.items()}


def _load_active() -> dict:
    out = _empty()
    with get_dash_engine().connect() as conn:
        rows = conn.execute(text(
            "SELECT kind, target_id FROM internal_targets WHERE deleted_at IS NULL"
        )).fetchall()
    for kind, tid in rows:
        if kind in KINDS:
            out[f"{kind}_ids"].add(int(tid))
    return out


def active_targets() -> dict:
    """집계용. 30초 캐시, 실패 시 마지막 정상값(없으면 빈 값)."""
    now = time.monotonic()
    with _lock:
        v = _cache["value"]
        if v is not None and now - _cache["at"] < CACHE_TTL_SEC:
            return _copy(v)
    try:
        v = _load_active()
    except Exception:  # noqa: BLE001
        logger.exception("직원식 대상 조회 실패 - 마지막 값 사용")
        with _lock:
            last = _cache["value"]
        return _copy(last or _empty())
    with _lock:
        _cache.update(at=now, value=v)
    return _copy(v)


def invalidate() -> None:
    with _lock:
        _cache.update(at=0.0, value=None)


def _rds_by_id(sql: str, ids) -> dict:
    ids = [int(i) for i in ids]
    if not ids:
        return {}
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(sql).bindparams(bindparam("ids", expanding=True)), {"ids": ids}
        ).mappings().all()
    return {int(r["id"]): dict(r) for r in rows}


def list_targets() -> list[dict]:
    with get_dash_engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT id, kind, target_id, label, memo, created_by, created_at
            FROM internal_targets
            WHERE deleted_at IS NULL
            ORDER BY kind, target_id
        """)).mappings().all()
    items = [dict(r) for r in rows]

    addr: dict = {}
    acc: dict = {}
    try:
        addr = _rds_by_id(SQL_ADDR_NAMES, [i["target_id"] for i in items if i["kind"] == "address"])
        acc = _rds_by_id(SQL_ACC_NAMES, [i["target_id"] for i in items if i["kind"] == "account"])
    except Exception:  # noqa: BLE001 - 이름 표시용, 실패해도 목록은 보여준다
        logger.exception("직원식 대상 이름 조회 실패")

    out = []
    for i in items:
        src = (addr if i["kind"] == "address" else acc).get(int(i["target_id"])) or {}
        out.append({
            "id": i["id"],
            "kind": i["kind"],
            "target_id": int(i["target_id"]),
            "label": i["label"],
            "name": src.get("name"),
            "account_id": src.get("account_id"),
            "account_name": src.get("account_name"),
            "memo": i["memo"],
            "created_by": i["created_by"],
            "created_at": i["created_at"].isoformat() if i["created_at"] else None,
        })
    return out


def search(kind: str, q: str) -> list[dict]:
    if kind not in KINDS:
        raise ValueError("kind는 address 또는 account 입니다")
    q = q.strip()
    if not q:
        return []
    params = {"q": f"%{q}%", "id": int(q) if q.isdigit() else -1}
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(SQL_SEARCH_ADDR if kind == "address" else SQL_SEARCH_ACC), params
        ).mappings().all()
    active = _load_active()[f"{kind}_ids"]
    out = []
    for r in rows:
        d = dict(r)
        d["id"] = int(d["id"])
        if "address_count" in d:
            d["address_count"] = int(d["address_count"] or 0)
        d["registered"] = d["id"] in active
        out.append(d)
    return out


def add_target(kind: str, target_id: int, memo: str | None, email: str) -> int:
    if kind not in KINDS:
        raise ValueError("kind는 address 또는 account 입니다")
    sql = SQL_ADDR_NAMES if kind == "address" else SQL_ACC_NAMES
    found = _rds_by_id(sql, [target_id]).get(int(target_id))
    if not found:
        raise ValueError(f"{KIND_LABEL[kind]} ID {target_id}를 찾을 수 없습니다")
    label = found.get("name")
    if kind == "address" and found.get("account_name"):
        label = f"{label} ({found['account_name']})"

    with get_dash_engine().begin() as conn:
        dup = conn.execute(text(
            "SELECT id FROM internal_targets "
            "WHERE kind = :k AND target_id = :t AND deleted_at IS NULL"
        ), {"k": kind, "t": int(target_id)}).fetchone()
        if dup:
            raise ValueError("이미 등록된 대상입니다")
        new_id = conn.execute(text(
            "INSERT INTO internal_targets (kind, target_id, label, memo, created_by) "
            "VALUES (:k, :t, :l, :m, :e) RETURNING id"
        ), {"k": kind, "t": int(target_id), "l": label, "m": memo, "e": email}).scalar_one()
    invalidate()
    return int(new_id)


def delete_target(item_id: int, email: str) -> None:
    with get_dash_engine().begin() as conn:
        res = conn.execute(text(
            "UPDATE internal_targets SET deleted_at = NOW(), deleted_by = :e "
            "WHERE id = :i AND deleted_at IS NULL"
        ), {"i": int(item_id), "e": email})
        if res.rowcount == 0:
            raise ValueError("대상을 찾을 수 없거나 이미 해제되었습니다")
    invalidate()
