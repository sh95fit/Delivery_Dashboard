"""S1-P1 차량 마스터 · 기간 비용(보험·세금 등) · 지출 내역(수리·감가 등)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import get_dash_engine
from app.services import dash_db
from app.services.cost_calc import allocate_period, days_incl, latest_by
from app.services.manager_service import today

FUEL_TYPES = ("gasoline", "diesel", "lpg", "ev")
PERIOD_CATS = ("insurance", "tax", "inspection", "other")
EXPENSE_CATS = ("repair", "maintenance", "tire", "depreciation", "parking", "wash", "other")
VEHICLE_FIELDS = ("plate_no", "model", "fuel_type", "fuel_efficiency", "purchase_date", "purchase_price", "memo", "active")
MAX_SUMMARY_DAYS = 400


def _iso(v):
    return v.isoformat() if v is not None else None


def vehicle_dict(body) -> dict:
    return {k: getattr(body, k) for k in VEHICLE_FIELDS}


def _clean_vehicle(d: dict) -> dict:
    d = {k: d.get(k) for k in VEHICLE_FIELDS}
    d["plate_no"] = (d["plate_no"] or "").strip()
    if not d["plate_no"]:
        raise ValueError("차량번호를 입력하세요")
    if d["fuel_type"] not in FUEL_TYPES:
        raise ValueError("연료 종류가 올바르지 않습니다")
    if d["fuel_efficiency"] is not None and d["fuel_efficiency"] <= 0:
        raise ValueError("연비는 0보다 커야 합니다")
    if d["purchase_price"] is not None and d["purchase_price"] < 0:
        raise ValueError("구매가는 0 이상이어야 합니다")
    d["model"] = (d["model"] or "").strip() or None
    d["memo"] = (d["memo"] or "").strip() or None
    d["active"] = True if d["active"] is None else bool(d["active"])
    return d


def _vehicle_out(r: dict, manager_ids: list[int]) -> dict:
    return {
        "id": r["id"], "plate_no": r["plate_no"], "model": r["model"], "fuel_type": r["fuel_type"],
        "fuel_efficiency": float(r["fuel_efficiency"]) if r["fuel_efficiency"] is not None else None,
        "purchase_date": _iso(r["purchase_date"]), "purchase_price": r["purchase_price"],
        "memo": r["memo"], "active": bool(r["active"]), "manager_ids": manager_ids,
    }


def list_vehicles() -> list[dict]:
    rows = dash_db.rows("SELECT * FROM vehicles WHERE deleted_at IS NULL ORDER BY active DESC, plate_no")
    cur = latest_by(
        dash_db.rows("SELECT manager_id, vehicle_id, start_date FROM vehicle_assignments WHERE deleted_at IS NULL"),
        "manager_id", "start_date", today(),
    )
    by_v: dict[int, list[int]] = {}
    for mid, a in cur.items():
        if a["vehicle_id"]:
            by_v.setdefault(a["vehicle_id"], []).append(mid)
    return [_vehicle_out(r, sorted(by_v.get(r["id"], []))) for r in rows]


def create_vehicle(data: dict, email: str) -> int:
    d = _clean_vehicle(data)
    try:
        return dash_db.insert_id("""
            INSERT INTO vehicles (plate_no, model, fuel_type, fuel_efficiency, purchase_date, purchase_price,
                                  memo, active, created_by, updated_by)
            VALUES (:plate_no, :model, :fuel_type, :fuel_efficiency, :purchase_date, :purchase_price,
                    :memo, :active, :e, :e)
            RETURNING id
        """, {**d, "e": email})
    except IntegrityError as exc:
        raise ValueError("이미 등록된 차량번호입니다") from exc


def update_vehicle(vid: int, data: dict, email: str) -> None:
    d = _clean_vehicle(data)
    try:
        with get_dash_engine().begin() as conn:
            res = conn.execute(text("""
                UPDATE vehicles
                   SET plate_no = :plate_no, model = :model, fuel_type = :fuel_type,
                       fuel_efficiency = :fuel_efficiency, purchase_date = :purchase_date,
                       purchase_price = :purchase_price, memo = :memo, active = :active,
                       updated_by = :e, updated_at = NOW()
                 WHERE id = :id AND deleted_at IS NULL
            """), {**d, "e": email, "id": vid})
    except IntegrityError as exc:
        raise ValueError("이미 등록된 차량번호입니다") from exc
    if res.rowcount == 0:
        raise ValueError("차량을 찾을 수 없습니다")


def _check_vehicle(vehicle_id: int) -> None:
    if not dash_db.rows("SELECT 1 FROM vehicles WHERE id = :v AND deleted_at IS NULL", {"v": vehicle_id}):
        raise ValueError("차량을 찾을 수 없습니다")


# ---------- 기간 비용 ----------
SQL_PERIOD = """
SELECT pc.*, v.plate_no FROM vehicle_period_costs pc
JOIN vehicles v ON v.id = pc.vehicle_id
WHERE pc.deleted_at IS NULL
"""


def _period_out(r: dict) -> dict:
    days = days_incl(r["start_date"], r["end_date"])
    return {
        "id": r["id"], "vehicle_id": r["vehicle_id"], "plate_no": r.get("plate_no"), "category": r["category"],
        "amount": int(r["amount"]), "start_date": _iso(r["start_date"]), "end_date": _iso(r["end_date"]),
        "days": days, "daily": round(int(r["amount"]) / days), "memo": r.get("memo"), "created_by": r.get("created_by"),
    }


def list_period_costs(vehicle_id: int | None) -> list[dict]:
    if vehicle_id:
        rows = dash_db.rows(SQL_PERIOD + " AND pc.vehicle_id = :v ORDER BY pc.start_date DESC, pc.id DESC",
                            {"v": vehicle_id})
    else:
        rows = dash_db.rows(SQL_PERIOD + " ORDER BY pc.start_date DESC, pc.id DESC")
    return [_period_out(r) for r in rows]


def add_period_cost(vehicle_id: int, category: str, amount: int, start: date, end: date,
                    memo: str | None, email: str) -> int:
    if category not in PERIOD_CATS:
        raise ValueError("항목이 올바르지 않습니다")
    if end < start:
        raise ValueError("종료일이 시작일보다 빠릅니다")
    if amount <= 0:
        raise ValueError("금액을 입력하세요")
    _check_vehicle(vehicle_id)
    return dash_db.insert_id("""
        INSERT INTO vehicle_period_costs (vehicle_id, category, amount, start_date, end_date, memo, created_by)
        VALUES (:v, :c, :a, :s, :t, :memo, :e) RETURNING id
    """, {"v": vehicle_id, "c": category, "a": amount, "s": start, "t": end, "memo": memo, "e": email})


# ---------- 지출 내역 ----------
SQL_EXPENSE = """
SELECT e.*, v.plate_no FROM vehicle_expenses e
JOIN vehicles v ON v.id = e.vehicle_id
WHERE e.deleted_at IS NULL AND e.expense_date BETWEEN :f AND :t
"""


def _expense_out(r: dict) -> dict:
    return {
        "id": r["id"], "vehicle_id": r["vehicle_id"], "plate_no": r.get("plate_no"),
        "expense_date": _iso(r["expense_date"]), "category": r["category"], "amount": int(r["amount"]),
        "memo": r.get("memo"), "created_by": r.get("created_by"),
    }


def list_expenses(frm: date, to: date, vehicle_id: int | None) -> list[dict]:
    if to < frm:
        raise ValueError("조회 종료일이 시작일보다 빠릅니다")
    params: dict = {"f": frm, "t": to}
    sql = SQL_EXPENSE
    if vehicle_id:
        sql += " AND e.vehicle_id = :v"
        params["v"] = vehicle_id
    return [_expense_out(r) for r in dash_db.rows(sql + " ORDER BY e.expense_date DESC, e.id DESC", params)]


def add_expense(vehicle_id: int, expense_date: date, category: str, amount: int, memo: str | None, email: str) -> int:
    if category not in EXPENSE_CATS:
        raise ValueError("항목이 올바르지 않습니다")
    if amount <= 0:
        raise ValueError("금액을 입력하세요")
    _check_vehicle(vehicle_id)
    return dash_db.insert_id("""
        INSERT INTO vehicle_expenses (vehicle_id, expense_date, category, amount, memo, created_by)
        VALUES (:v, :d, :c, :a, :memo, :e) RETURNING id
    """, {"v": vehicle_id, "d": expense_date, "c": category, "a": amount, "memo": memo, "e": email})


# ---------- 기간 요약 (비용 엔진 P6의 차량 부분) ----------
def cost_summary(frm: date, to: date) -> dict:
    if to < frm:
        raise ValueError("조회 종료일이 시작일보다 빠릅니다")
    if days_incl(frm, to) > MAX_SUMMARY_DAYS:
        raise ValueError(f"조회 기간은 {MAX_SUMMARY_DAYS}일 이내로 지정하세요")
    vehicles = {r["id"]: r for r in dash_db.rows("SELECT id, plate_no, active, deleted_at FROM vehicles")}
    periods = dash_db.rows("""
        SELECT vehicle_id, amount, start_date, end_date FROM vehicle_period_costs
        WHERE deleted_at IS NULL AND start_date <= :t AND end_date >= :f
    """, {"f": frm, "t": to})
    expenses = dash_db.rows("""
        SELECT vehicle_id, category, amount FROM vehicle_expenses
        WHERE deleted_at IS NULL AND expense_date BETWEEN :f AND :t
    """, {"f": frm, "t": to})

    acc: dict[int, dict] = {}

    def slot(vid: int) -> dict:
        return acc.setdefault(vid, {
            "vehicle_id": vid, "plate_no": (vehicles.get(vid) or {}).get("plate_no"),
            "period_cost": 0, "expense": 0, "expense_by_category": {},
        })

    for vid, v in vehicles.items():
        if v["deleted_at"] is None and v["active"]:
            slot(vid)
    for p in periods:
        slot(p["vehicle_id"])["period_cost"] += allocate_period(p["amount"], p["start_date"], p["end_date"], frm, to)
    for e in expenses:
        s = slot(e["vehicle_id"])
        s["expense"] += int(e["amount"])
        s["expense_by_category"][e["category"]] = s["expense_by_category"].get(e["category"], 0) + int(e["amount"])

    items = sorted(acc.values(), key=lambda x: x["plate_no"] or "")
    return {
        "from": frm.isoformat(), "to": to.isoformat(), "days": days_incl(frm, to),
        "vehicles": items,
        "totals": {"period_cost": sum(i["period_cost"] for i in items), "expense": sum(i["expense"] for i in items)},
    }
