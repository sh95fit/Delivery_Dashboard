"""S2-P0b 인력(사람) 마스터: 기본 정보 · 계약 조건 이력 · 고정 계정 이력 (dash_db).
운영 계정(manager)은 이름·색 표시용으로만 읽는다 (운영 DB 장애여도 화면은 열림).
insert_rate / account_holder / insert_account 는 일괄 등록(worker_import)과 공용."""
from __future__ import annotations

from datetime import date

from sqlalchemy import text

from app.database import get_dash_engine
from app.services import dash_db
from app.services.cost_calc import latest_by
from app.services.manager_service import _hm, _iso, _rds_managers, today
from app.services.worker_calc import check_rate, day_calc

SQL_RATES = "SELECT * FROM worker_pay_rates WHERE deleted_at IS NULL"
SQL_ACCOUNTS = "SELECT * FROM worker_accounts WHERE deleted_at IS NULL"


def _managers() -> dict[int, dict]:
    try:
        return {m["manager_id"]: m for m in _rds_managers()}
    except Exception:  # noqa: BLE001
        return {}


def rate_out(r: dict) -> dict:
    pt = r["pay_type"]
    amount = int(r["amount"] or 0)
    d = day_calc(r.get("work_start"), r.get("work_end"), break_min=int(r.get("break_min") or 0),
                 break_paid=bool(r.get("break_paid")), work_start=None, work_end=None)
    return {
        "id": r["id"], "effective_from": _iso(r["effective_from"]), "pay_type": pt, "amount": amount,
        "vat_applied": bool(r.get("vat_applied")),
        "work_start": _hm(r.get("work_start")), "work_end": _hm(r.get("work_end")),
        "break_min": int(r.get("break_min") or 0), "break_paid": bool(r.get("break_paid")),
        "ot_unit_min": int(r.get("ot_unit_min") or 0), "ot_unit_amount": int(r.get("ot_unit_amount") or 0),
        "paid_min": d["paid"],
        "daily_base": (amount * d["paid"] + 30) // 60 if pt == "hourly" else None,
        "memo": r.get("memo"), "created_by": r.get("created_by"),
    }


def account_out(a: dict, mgrs: dict[int, dict]) -> dict:
    mid = a["manager_id"]
    m = mgrs.get(mid) if mid is not None else None
    return {"id": a["id"], "manager_id": mid, "start_date": _iso(a["start_date"]),
            "manager_name": (m or {}).get("name"), "manager_color": (m or {}).get("color"),
            "created_by": a.get("created_by")}


def list_workers() -> list[dict]:
    d = today()
    mgrs = _managers()
    ws = dash_db.rows("SELECT * FROM workers WHERE deleted_at IS NULL ORDER BY id")
    rates = latest_by(dash_db.rows(SQL_RATES), "worker_id", "effective_from", d)
    accs = latest_by(dash_db.rows(SQL_ACCOUNTS), "worker_id", "start_date", d)
    out = []
    for w in ws:
        wid = w["id"]
        a = accs.get(wid)
        out.append({
            "id": wid, "name": w["name"], "income_type": w["income_type"], "active": bool(w["active"]),
            "memo": w.get("memo"), "legacy_manager_id": w.get("legacy_manager_id"),
            "updated_at": _iso(w.get("updated_at")), "updated_by": w.get("updated_by"),
            "rate": rate_out(rates[wid]) if wid in rates else None,
            "account": account_out(a, mgrs) if a and a["manager_id"] is not None else None,
        })
    return out


def worker_detail(wid: int) -> dict:
    mgrs = _managers()
    rates = dash_db.rows(SQL_RATES + " AND worker_id = :w ORDER BY effective_from DESC", {"w": wid})
    accs = dash_db.rows(SQL_ACCOUNTS + " AND worker_id = :w ORDER BY start_date DESC", {"w": wid})
    return {"rates": [rate_out(r) for r in rates], "accounts": [account_out(a, mgrs) for a in accs]}


def save_worker(wid: int | None, name: str, income_type: str, active: bool, memo: str | None, email: str) -> int:
    name = (name or "").strip()
    if not name:
        raise ValueError("이름을 입력하세요")
    with get_dash_engine().begin() as conn:
        dup = conn.execute(text(
            "SELECT 1 FROM workers WHERE name = :n AND deleted_at IS NULL AND id <> :w"
        ), {"n": name, "w": wid or 0}).fetchone()
        if dup:
            raise ValueError("같은 이름의 인력이 이미 있습니다. 동명이인은 '김민수B'처럼 구분해 입력하세요")
        p = {"n": name, "t": income_type, "a": active, "m": memo, "e": email}
        if wid is None:
            return int(conn.execute(text("""
                INSERT INTO workers (name, income_type, active, memo, created_by, updated_by)
                VALUES (:n, :t, :a, :m, :e, :e) RETURNING id
            """), p).scalar_one())
        res = conn.execute(text("""
            UPDATE workers SET name = :n, income_type = :t, active = :a, memo = :m,
                   updated_by = :e, updated_at = NOW()
            WHERE id = :w AND deleted_at IS NULL
        """), {**p, "w": wid})
        if res.rowcount == 0:
            raise ValueError("인력을 찾을 수 없습니다")
        return wid


def insert_rate(conn, wid: int, r: dict, email: str) -> int:
    """check_rate를 통과한 값 r 저장. 같은 적용 시작일이 있으면 ValueError."""
    dup = conn.execute(text("""
        SELECT 1 FROM worker_pay_rates
        WHERE worker_id = :w AND effective_from = :f AND deleted_at IS NULL
    """), {"w": wid, "f": r["effective_from"]}).fetchone()
    if dup:
        raise ValueError("같은 적용 시작일의 계약 조건이 이미 있습니다. 기존 행을 삭제한 뒤 입력하세요")
    return int(conn.execute(text("""
        INSERT INTO worker_pay_rates
            (worker_id, effective_from, pay_type, amount, vat_applied, work_start, work_end,
             break_min, break_paid, ot_unit_min, ot_unit_amount, memo, created_by)
        VALUES (:w, :f, :t, :a, :v, :ws, :we, :bm, :bp, :um, :ua, :memo, :e) RETURNING id
    """), {"w": wid, "f": r["effective_from"], "t": r["pay_type"], "a": r["amount"],
           "v": r["vat_applied"], "ws": r.get("work_start"), "we": r.get("work_end"),
           "bm": r["break_min"], "bp": r["break_paid"], "um": r["ot_unit_min"],
           "ua": r["ot_unit_amount"], "memo": r.get("memo"), "e": email}).scalar_one())


def add_rate(wid: int, body: dict, email: str) -> int:
    with get_dash_engine().begin() as conn:
        w = conn.execute(text("SELECT income_type FROM workers WHERE id = :w AND deleted_at IS NULL"),
                         {"w": wid}).fetchone()
        if not w:
            raise ValueError("인력을 찾을 수 없습니다")
        return insert_rate(conn, wid, check_rate(w[0], body), email)


def account_holder(conn, wid: int | None, manager_id: int, start_date: date) -> str | None:
    """start_date 기준 이 계정을 고정 사용 중인 다른 활성 인력 이름 (같은 트랜잭션의 미확정 행 포함)."""
    others = [dict(r) for r in conn.execute(text("""
        SELECT a.worker_id, a.manager_id, a.start_date, w.name
        FROM worker_accounts a
        JOIN workers w ON w.id = a.worker_id AND w.deleted_at IS NULL AND w.active
        WHERE a.deleted_at IS NULL AND a.worker_id <> :w
    """), {"w": wid or 0}).mappings().all()]
    cur = latest_by(others, "worker_id", "start_date", start_date)
    return next((r["name"] for r in cur.values() if r["manager_id"] == manager_id), None)


def insert_account(conn, wid: int, manager_id: int | None, start_date: date, email: str) -> int:
    conn.execute(text("""
        UPDATE worker_accounts SET deleted_at = NOW(), deleted_by = :e
        WHERE worker_id = :w AND start_date = :s AND deleted_at IS NULL
    """), {"w": wid, "s": start_date, "e": email})
    return int(conn.execute(text("""
        INSERT INTO worker_accounts (worker_id, manager_id, start_date, created_by)
        VALUES (:w, :m, :s, :e) RETURNING id
    """), {"w": wid, "m": manager_id, "s": start_date, "e": email}).scalar_one())


def assign_account(wid: int, manager_id: int | None, start_date: date, email: str) -> int:
    with get_dash_engine().begin() as conn:
        if not conn.execute(text("SELECT 1 FROM workers WHERE id = :w AND deleted_at IS NULL"),
                            {"w": wid}).fetchone():
            raise ValueError("인력을 찾을 수 없습니다")
        if manager_id is not None:
            holder = account_holder(conn, wid, manager_id, start_date)
            if holder:
                raise ValueError(f"{start_date} 기준 '{holder}'님이 이 계정을 고정 사용 중입니다. "
                                 "그 사람의 계정을 먼저 바꾸세요 (하루만 바뀌는 경우는 근무 입력의 일 단위 예외로 처리)")
        return insert_account(conn, wid, manager_id, start_date, email)



def update_rate(rid: int, body: dict, email: str) -> int:
    """계약 이력 수정 = 기존 행 삭제 표시 + 새 행 저장 (한 트랜잭션 → 변경 기록 보존). 새 행 id 반환."""
    with get_dash_engine().begin() as conn:
        old = conn.execute(text("""
            SELECT r.worker_id, w.income_type FROM worker_pay_rates r
            JOIN workers w ON w.id = r.worker_id AND w.deleted_at IS NULL
            WHERE r.id = :r AND r.deleted_at IS NULL
        """), {"r": rid}).fetchone()
        if not old:
            raise ValueError("계약 이력을 찾을 수 없습니다 (이미 수정·삭제됨 — 새로고침하세요)")
        wid = int(old[0])
        r = check_rate(old[1], body)
        dup = conn.execute(text("""
            SELECT 1 FROM worker_pay_rates
            WHERE worker_id = :w AND effective_from = :f AND deleted_at IS NULL AND id <> :r
        """), {"w": wid, "f": r["effective_from"], "r": rid}).fetchone()
        if dup:
            raise ValueError(f"{r['effective_from']}에 시작하는 다른 계약이 이미 있습니다. 그 행을 수정하세요")
        conn.execute(text("UPDATE worker_pay_rates SET deleted_at = NOW(), deleted_by = :e WHERE id = :r"),
                     {"r": rid, "e": email})
        return insert_rate(conn, wid, r, email)


def update_account(aid: int, manager_id: int | None, start_date: date, email: str) -> int:
    """고정 계정 이력 수정 (계정·시작일). 방식은 update_rate와 같음."""
    with get_dash_engine().begin() as conn:
        old = conn.execute(text("""
            SELECT a.worker_id FROM worker_accounts a
            JOIN workers w ON w.id = a.worker_id AND w.deleted_at IS NULL
            WHERE a.id = :a AND a.deleted_at IS NULL
        """), {"a": aid}).fetchone()
        if not old:
            raise ValueError("계정 이력을 찾을 수 없습니다 (이미 수정·삭제됨 — 새로고침하세요)")
        wid = int(old[0])
        dup = conn.execute(text("""
            SELECT 1 FROM worker_accounts
            WHERE worker_id = :w AND start_date = :s AND deleted_at IS NULL AND id <> :a
        """), {"w": wid, "s": start_date, "a": aid}).fetchone()
        if dup:
            raise ValueError(f"{start_date}에 시작하는 다른 계정 이력이 이미 있습니다. 그 행을 수정하세요")
        if manager_id is not None:
            holder = account_holder(conn, wid, manager_id, start_date)
            if holder:
                raise ValueError(f"{start_date} 기준 '{holder}'님이 이 계정을 고정 사용 중입니다. "
                                 "그 사람의 계정을 먼저 바꾸세요")
        conn.execute(text("UPDATE worker_accounts SET deleted_at = NOW(), deleted_by = :e WHERE id = :a"),
                     {"a": aid, "e": email})
        return insert_account(conn, wid, manager_id, start_date, email)
