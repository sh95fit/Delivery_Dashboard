"""S1-P1 매니저 마스터.
- 이름·색: 운영 DB manager (읽기 전용)
- 급여·차량 배정·메모: dash_db. 급여·차량은 '적용 시작일' 이력 → 과거 날짜 비용도 당시 기준
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import text

from app.database import get_dash_engine, get_engine
from app.services import dash_db
from app.services.cost_calc import latest_by
from app.services.day_aggregate import KST

PAY_TYPES = ("monthly", "hourly", "none")
RECENT_DAYS = 30

SQL_MANAGERS = "SELECT id, name, color FROM manager ORDER BY id"
SQL_RECENT = """
SELECT manager_id, COUNT(*) AS n, MAX(date) AS last_date
FROM delivery
WHERE date >= :d AND deleted_at IS NULL AND manager_id IS NOT NULL
GROUP BY manager_id
"""
SQL_ASSIGN = """
SELECT va.id, va.manager_id, va.vehicle_id, va.start_date, va.created_by, v.plate_no, v.model
FROM vehicle_assignments va
LEFT JOIN vehicles v ON v.id = va.vehicle_id
WHERE va.deleted_at IS NULL
"""


def today() -> date:
    return datetime.now(KST).date()


def _iso(v):
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def rate_out(r: dict) -> dict:
    return {"id": r["id"], "pay_type": r["pay_type"], "amount": int(r["amount"] or 0),
            "effective_from": _iso(r["effective_from"]), "memo": r.get("memo"), "created_by": r.get("created_by")}


def assign_out(r: dict) -> dict:
    return {"id": r["id"], "vehicle_id": r["vehicle_id"], "plate_no": r.get("plate_no"), "model": r.get("model"),
            "start_date": _iso(r["start_date"]), "created_by": r.get("created_by")}


def _rds_managers() -> list[dict]:
    with get_engine().connect() as conn:
        base = conn.execute(text(SQL_MANAGERS)).mappings().all()
        recent = conn.execute(text(SQL_RECENT), {"d": today() - timedelta(days=RECENT_DAYS)}).mappings().all()
    rc = {int(r["manager_id"]): r for r in recent}
    out = []
    for r in base:
        c = rc.get(int(r["id"]))
        out.append({
            "manager_id": int(r["id"]), "name": r["name"], "color": r["color"],
            "recent_stops": int(c["n"]) if c else 0,
            "last_date": _iso(c["last_date"]) if c else None,
        })
    return out


def list_managers() -> list[dict]:
    d = today()
    base = _rds_managers()
    profiles = {r["manager_id"]: r for r in dash_db.rows("SELECT manager_id, active, memo FROM manager_profiles")}
    pay = latest_by(dash_db.rows("SELECT * FROM manager_pay_rates WHERE deleted_at IS NULL"),
                    "manager_id", "effective_from", d)
    veh = latest_by(dash_db.rows(SQL_ASSIGN), "manager_id", "start_date", d)
    for m in base:
        mid = m["manager_id"]
        p = profiles.get(mid) or {}
        m["active"] = bool(p.get("active", True))
        m["memo"] = p.get("memo")
        m["pay"] = rate_out(pay[mid]) if mid in pay else None
        a = veh.get(mid)
        m["vehicle"] = ({"vehicle_id": a["vehicle_id"], "plate_no": a["plate_no"], "model": a["model"]}
                        if a and a["vehicle_id"] else None)
    return base


def manager_detail(mid: int) -> dict:
    rates = dash_db.rows(
        "SELECT * FROM manager_pay_rates WHERE manager_id = :m AND deleted_at IS NULL ORDER BY effective_from DESC",
        {"m": mid},
    )
    assigns = dash_db.rows(SQL_ASSIGN + " AND va.manager_id = :m ORDER BY va.start_date DESC", {"m": mid})
    return {"rates": [rate_out(r) for r in rates], "assignments": [assign_out(a) for a in assigns]}


def save_profile(mid: int, active: bool, memo: str | None, email: str) -> None:
    with get_dash_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO manager_profiles (manager_id, active, memo, updated_by, updated_at)
            VALUES (:m, :a, :memo, :e, NOW())
            ON CONFLICT (manager_id) DO UPDATE
               SET active = EXCLUDED.active, memo = EXCLUDED.memo,
                   updated_by = EXCLUDED.updated_by, updated_at = NOW()
        """), {"m": mid, "a": active, "memo": memo, "e": email})


def add_rate(mid: int, pay_type: str, amount: int, effective_from: date, memo: str | None, email: str) -> int:
    if pay_type not in PAY_TYPES:
        raise ValueError("급여 유형이 올바르지 않습니다")
    amount = 0 if pay_type == "none" else int(amount or 0)
    if pay_type != "none" and amount <= 0:
        raise ValueError("금액을 입력하세요")
    with get_dash_engine().begin() as conn:
        dup = conn.execute(text(
            "SELECT 1 FROM manager_pay_rates WHERE manager_id = :m AND effective_from = :f AND deleted_at IS NULL"
        ), {"m": mid, "f": effective_from}).fetchone()
        if dup:
            raise ValueError("같은 적용 시작일의 급여가 이미 있습니다. 기존 행을 삭제한 뒤 입력하세요")
        return int(conn.execute(text("""
            INSERT INTO manager_pay_rates (manager_id, pay_type, amount, effective_from, memo, created_by)
            VALUES (:m, :t, :a, :f, :memo, :e) RETURNING id
        """), {"m": mid, "t": pay_type, "a": amount, "f": effective_from, "memo": memo, "e": email}).scalar_one())


def assign_vehicle(mid: int, vehicle_id: int | None, start_date: date, email: str) -> int:
    with get_dash_engine().begin() as conn:
        if vehicle_id is not None:
            ok = conn.execute(text("SELECT 1 FROM vehicles WHERE id = :v AND deleted_at IS NULL"),
                              {"v": vehicle_id}).fetchone()
            if not ok:
                raise ValueError("차량을 찾을 수 없습니다")
        # 같은 시작일 배정은 교체
        conn.execute(text("""
            UPDATE vehicle_assignments SET deleted_at = NOW(), deleted_by = :e
            WHERE manager_id = :m AND start_date = :s AND deleted_at IS NULL
        """), {"m": mid, "s": start_date, "e": email})
        return int(conn.execute(text("""
            INSERT INTO vehicle_assignments (manager_id, vehicle_id, start_date, created_by)
            VALUES (:m, :v, :s, :e) RETURNING id
        """), {"m": mid, "v": vehicle_id, "s": start_date, "e": email}).scalar_one())
