"""S1-P1 매니저 마스터.
- 이름·색: 운영 DB manager (읽기 전용). 색이 없거나 형식이 틀리면 대시보드와 같은 대체 색
- 급여·근무 기준·차량 배정·메모: dash_db. 급여·차량은 '적용 시작일' 이력 → 과거 날짜 비용도 당시 기준
- 시급제 근무 기준(시작·종료·휴게)은 예상 물류비용용. 실제 출퇴근은 근무일지 단계에서 별도 기록
"""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import text

from app.database import get_dash_engine, get_engine
from app.services import dash_db
from app.services.cost_calc import hourly_daily_cost, latest_by, paid_minutes
from app.services.day_aggregate import KST, manager_color

PAY_TYPES = ("monthly", "hourly", "none")

SQL_MANAGERS = "SELECT id, name, color FROM manager ORDER BY id"
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


def _hm(v):
    if v is None:
        return None
    return v.strftime("%H:%M") if hasattr(v, "strftime") else str(v)[:5]


def rate_out(r: dict) -> dict:
    pay_type = r["pay_type"]
    amount = int(r["amount"] or 0)
    ws, we = r.get("work_start"), r.get("work_end")
    bm, bp = int(r.get("break_min") or 0), bool(r.get("break_paid"))
    pm = paid_minutes(ws, we, bm, bp) if pay_type == "hourly" else 0
    return {
        "id": r["id"], "pay_type": pay_type, "amount": amount,
        "effective_from": _iso(r["effective_from"]), "memo": r.get("memo"), "created_by": r.get("created_by"),
        "work_start": _hm(ws), "work_end": _hm(we), "break_min": bm, "break_paid": bp,
        "paid_min": pm,
        "daily_cost": hourly_daily_cost(amount, pm) if pay_type == "hourly" else None,
    }


def assign_out(r: dict) -> dict:
    return {"id": r["id"], "vehicle_id": r["vehicle_id"], "plate_no": r.get("plate_no"), "model": r.get("model"),
            "start_date": _iso(r["start_date"]), "created_by": r.get("created_by")}


def _rds_managers() -> list[dict]:
    with get_engine().connect() as conn:
        base = conn.execute(text(SQL_MANAGERS)).mappings().all()
    return [{"manager_id": int(r["id"]), "name": r["name"], "color": manager_color(r["id"], r["color"])}
            for r in base]


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


def add_rate(mid: int, pay_type: str, amount: int, effective_from: date, memo: str | None, email: str,
             *, work_start: time | None = None, work_end: time | None = None,
             break_min: int = 0, break_paid: bool = False) -> int:
    if pay_type not in PAY_TYPES:
        raise ValueError("급여 유형이 올바르지 않습니다")
    amount = 0 if pay_type == "none" else int(amount or 0)
    if pay_type != "none" and amount <= 0:
        raise ValueError("금액을 입력하세요")
    if pay_type == "hourly":
        if work_start is None or work_end is None:
            raise ValueError("시급제는 근무 시작·종료 시각을 입력하세요")
        if paid_minutes(work_start, work_end, 0, True) <= 0:
            raise ValueError("종료 시각은 시작 시각보다 늦어야 합니다 (자정을 넘는 근무는 지원하지 않습니다)")
        if paid_minutes(work_start, work_end, break_min, False) <= 0:
            raise ValueError("휴게시간이 근무시간보다 깁니다")
    else:
        work_start = work_end = None
        break_min, break_paid = 0, False
    with get_dash_engine().begin() as conn:
        dup = conn.execute(text(
            "SELECT 1 FROM manager_pay_rates WHERE manager_id = :m AND effective_from = :f AND deleted_at IS NULL"
        ), {"m": mid, "f": effective_from}).fetchone()
        if dup:
            raise ValueError("같은 적용 시작일의 급여가 이미 있습니다. 기존 행을 삭제한 뒤 입력하세요")
        return int(conn.execute(text("""
            INSERT INTO manager_pay_rates
                (manager_id, pay_type, amount, effective_from, memo, created_by,
                 work_start, work_end, break_min, break_paid)
            VALUES (:m, :t, :a, :f, :memo, :e, :ws, :we, :bm, :bp) RETURNING id
        """), {"m": mid, "t": pay_type, "a": amount, "f": effective_from, "memo": memo, "e": email,
               "ws": work_start, "we": work_end, "bm": int(break_min or 0), "bp": bool(break_paid)}).scalar_one())


def assign_vehicle(mid: int, vehicle_id: int | None, start_date: date, email: str) -> int:
    with get_dash_engine().begin() as conn:
        if vehicle_id is not None:
            ok = conn.execute(text("SELECT 1 FROM vehicles WHERE id = :v AND deleted_at IS NULL"),
                              {"v": vehicle_id}).fetchone()
            if not ok:
                raise ValueError("차량을 찾을 수 없습니다")
        conn.execute(text("""
            UPDATE vehicle_assignments SET deleted_at = NOW(), deleted_by = :e
            WHERE manager_id = :m AND start_date = :s AND deleted_at IS NULL
        """), {"m": mid, "s": start_date, "e": email})
        return int(conn.execute(text("""
            INSERT INTO vehicle_assignments (manager_id, vehicle_id, start_date, created_by)
            VALUES (:m, :v, :s, :e) RETURNING id
        """), {"m": mid, "v": vehicle_id, "s": start_date, "e": email}).scalar_one())
