"""S3-P1b-2b 주유 기록 · 유류비 월 마감.

- 주유 기록 = 날짜, 차량, 합계(공급가액·부가세), 수량(리터, 전기차는 kWh)
- 비용 = 부가세 공제 차량은 공급가액, 불공제 차량은 합계 (fuel_log_calc.log_cost)
- 물류비 = 그달 차량별 비용을 그달 영업일로 나눠, 그날 그 차량에 배정된 계정에 똑같이 나눔
- 마감한 달 = 확정(fuel), 마감 전 = 지금까지 입력한 기록으로 예상(fuel_est)
- 마감한 달은 추가·삭제 불가. 해제는 사유 필수, 이력 보존
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import get_dash_engine
from app.services import dash_db
from app.services.assign_service import Assign
from app.services.calendar_service import open_checker
from app.services.cost_calc import latest_by
from app.services.fuel_calc import add_basis, finish_basis, ref_price
from app.services.fuel_log_calc import allocate_month, amounts, days_between, log_cost, month_bounds
from app.services.logistics_calc import split_even
from app.services.manager_service import today
from app.services.route_fuel_calc import overrun

FUEL_LABEL = {"gasoline": "휘발유", "diesel": "경유", "lpg": "LPG", "ev": "전기"}

SQL_LOGS = """
SELECT l.*, v.plate_no, v.vat_deductible
FROM fuel_logs l JOIN vehicles v ON v.id = l.vehicle_id
WHERE l.deleted_at IS NULL AND l.fuel_date BETWEEN :f AND :t
"""
SQL_ASSIGNS = "SELECT manager_id, vehicle_id, start_date FROM vehicle_assignments WHERE deleted_at IS NULL"


def _iso(v):
    return v.isoformat() if v is not None else None


def _num(v):
    return float(v) if v is not None else None


def _text(v):
    return (str(v).strip() or None) if v is not None else None


def _ym(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


# ---------- 마감 ----------
def _closing(first: date) -> dict | None:
    rows = dash_db.rows("""
        SELECT id, close_month, total_amount, cost_amount, log_count, memo, closed_by, closed_at
        FROM fuel_closings WHERE close_month = :m AND released_at IS NULL
    """, {"m": first})
    return rows[0] if rows else None


def _closing_out(c: dict | None) -> dict | None:
    if not c:
        return None
    return {"total_amount": int(c["total_amount"]), "cost_amount": int(c["cost_amount"]),
            "log_count": int(c["log_count"]), "memo": c.get("memo"),
            "closed_by": c.get("closed_by"), "closed_at": _iso(c.get("closed_at"))}


def _check_unclosed(d: date) -> None:
    if _closing(d.replace(day=1)):
        raise ValueError(f"{d.year}년 {d.month}월 유류비는 마감됐습니다 — 마감 해제 후 수정하세요")


def users_on(assigns: list[dict], d: date) -> dict[int, list[int]]:
    """그날 차량별 배정 계정 목록 (차량 배정 이력의 그날 기준)."""
    out: dict[int, list[int]] = {}
    for mid, a in latest_by(assigns, "manager_id", "start_date", d).items():
        if a["vehicle_id"]:
            out.setdefault(a["vehicle_id"], []).append(mid)
    return out


# ---------- 주유 기록 ----------
def _log_out(r: dict) -> dict:
    return {
        "id": r["id"], "vehicle_id": r["vehicle_id"], "plate_no": r.get("plate_no"),
        "fuel_date": _iso(r["fuel_date"]), "fuel_type": r["fuel_type"],
        "quantity": _num(r.get("quantity")), "unit_price": _num(r.get("unit_price")),
        "total_amount": int(r["total_amount"]), "supply_amount": int(r["supply_amount"]),
        "vat_amount": int(r["vat_amount"]), "cost": log_cost(r, bool(r.get("vat_deductible"))),
        "station": r.get("station"), "memo": r.get("memo"), "source": r["source"],
        "created_by": r.get("created_by"),
    }


def price_rows(f: date, t: date) -> list[dict]:
    """주유일 기준 단가용 — 그달 + 앞 31일 (그날 값이 없으면 바로 전 날짜 값)."""
    return dash_db.rows("""SELECT price_date, fuel_type, price, source FROM fuel_price_log
        WHERE deleted_at IS NULL AND price_date BETWEEN :a AND :t""", {"a": f - timedelta(days=31), "t": t})


def log_ref(r: dict, prices: list[dict]) -> dict:
    """주유 기록 1건의 오피넷(또는 직접 입력) 기준 단가 · 차이. 단가가 없으면 합계 ÷ 수량."""
    unit = r.get("unit_price")
    if not unit and r.get("quantity"):
        unit = int(r["total_amount"]) / float(r["quantity"])
    return ref_price(prices, r["fuel_type"], r["fuel_date"], unit)


def list_logs(month: str, vehicle_id: int | None = None) -> dict:
    f, t = month_bounds(month)
    sql, p = SQL_LOGS, {"f": f, "t": t}
    if vehicle_id:
        sql += " AND l.vehicle_id = :v"
        p["v"] = vehicle_id
    rows = dash_db.rows(sql + " ORDER BY l.fuel_date, v.plate_no, l.id", p)
    prices = price_rows(f, t)
    return {"month": _ym(f), "closed": _closing_out(_closing(f)),
            "items": [{**_log_out(r), **log_ref(r, prices)} for r in rows]}


def add_log(data: dict, email: str, source: str = "manual") -> int:
    d = data["fuel_date"]
    if d > today():
        raise ValueError("미래 날짜는 입력할 수 없습니다")
    v = dash_db.rows("SELECT id, fuel_type FROM vehicles WHERE id = :v AND deleted_at IS NULL",
                     {"v": data["vehicle_id"]})
    if not v:
        raise ValueError("차량을 찾을 수 없습니다")
    vft = v[0]["fuel_type"]
    ft = data.get("fuel_type") or vft
    if ft != vft:
        raise ValueError(f"차량 연료({FUEL_LABEL.get(vft, vft)})와 입력한 연료({FUEL_LABEL.get(ft, ft)})가 다릅니다"
                         " — 차량 정보를 확인하세요")
    total, supply, vat = amounts(data["total_amount"], data.get("supply_amount"), data.get("vat_amount"))
    _check_unclosed(d)
    return dash_db.insert_id("""
        INSERT INTO fuel_logs (vehicle_id, fuel_date, fuel_type, quantity, unit_price, total_amount,
                               supply_amount, vat_amount, station, memo, source, created_by)
        VALUES (:v, :d, :ft, :q, :u, :tot, :sup, :vat, :st, :memo, :src, :e)
        RETURNING id
    """, {"v": data["vehicle_id"], "d": d, "ft": ft, "q": data.get("quantity"), "u": data.get("unit_price"),
          "tot": total, "sup": supply, "vat": vat, "st": _text(data.get("station")),
          "memo": _text(data.get("memo")), "src": source, "e": email})


def delete_log(lid: int, email: str) -> None:
    rows = dash_db.rows("SELECT fuel_date FROM fuel_logs WHERE id = :i AND deleted_at IS NULL", {"i": lid})
    if not rows:
        raise ValueError("주유 기록을 찾을 수 없습니다 (이미 삭제됨 — 새로고침하세요)")
    _check_unclosed(rows[0]["fuel_date"])
    with get_dash_engine().begin() as conn:
        conn.execute(text("UPDATE fuel_logs SET deleted_at = NOW(), deleted_by = :e "
                          "WHERE id = :i AND deleted_at IS NULL"), {"e": email, "i": lid})


# ---------- 월 집계 ----------
def _zero(**kw) -> dict:
    return {**kw, "count": 0, "quantity": 0.0, "total": 0, "supply": 0, "vat": 0, "cost": 0}


def _add(acc: dict, r: dict, cost: int) -> None:
    acc["count"] += 1
    acc["quantity"] += float(r["quantity"] or 0)
    acc["total"] += int(r["total_amount"])
    acc["supply"] += int(r["supply_amount"])
    acc["vat"] += int(r["vat_amount"])
    acc["cost"] += cost


def month_summary(month: str) -> dict:
    """차량별 · 일자별(주유한 날) · 계정별(영업일 배분 후 차량 배정 계정에 균분). 계정 이름은 화면에서 붙임."""
    f, t = month_bounds(month)
    rows = dash_db.rows(SQL_LOGS + " ORDER BY l.fuel_date, l.id", {"f": f, "t": t})
    prices = price_rows(f, t)
    is_open = open_checker(f, t)
    open_days = [x for x in days_between(f, t) if is_open(x)]
    totals = _zero()
    by_v: dict[int, dict] = {}
    by_d: dict[date, dict] = {}
    for r in rows:
        cost = log_cost(r, bool(r["vat_deductible"]))
        _add(totals, r, cost)
        _add(by_v.setdefault(r["vehicle_id"], _zero(
            vehicle_id=r["vehicle_id"], plate_no=r["plate_no"], fuel_type=r["fuel_type"],
            vat_deductible=bool(r["vat_deductible"]))), r, cost)
        add_basis(by_v[r["vehicle_id"]], r["quantity"], r["total_amount"], log_ref(r, prices)["ref_price"])
        _add(by_d.setdefault(r["fuel_date"], _zero(date=_iso(r["fuel_date"]))), r, cost)

    asg = Assign(f, t)   # [S3-P2h-1b] 날짜별 계정 → 인력 → 차량
    # [S3-P2e-2] 초과 주행: 주유량 × 차량 연비 − 경로 기록 거리(그날 그 차량을 배정받은 매니저의 실제 경로)
    eff = {r["id"]: r["fuel_efficiency"] for r in dash_db.rows("SELECT id, fuel_efficiency FROM vehicles")}
    route_m: dict[int, int] = {}
    for r in dash_db.rows("""SELECT route_date, manager_id, SUM(distance_m) AS m FROM route_legs
            WHERE route_date BETWEEN :f AND :t GROUP BY route_date, manager_id""", {"f": f, "t": t}):
        vid = asg.vehicle(r["route_date"], int(r["manager_id"]))
        if vid:
            route_m[vid] = route_m.get(vid, 0) + int(r["m"] or 0)
    over = {vid: {**overrun(x["quantity"], eff.get(vid), route_m.get(vid)),
                  "fuel_efficiency": float(eff[vid]) if eff.get(vid) is not None else None}
            for vid, x in by_v.items()}    
    by_m: dict = {}    
    alloc = allocate_month({vid: x["cost"] for vid, x in by_v.items()}, open_days, f, t)
    for d, per_vid in alloc.items():
        users = asg.users(d)
        for vid, amt in per_vid.items():
            shares = split_even(amt, users[vid]) if users.get(vid) else {None: amt}
            for mid, share in shares.items():
                m = by_m.setdefault(mid, {"manager_id": mid, "cost": 0, "vehicle_ids": set()})
                m["cost"] += share
                m["vehicle_ids"].add(vid)
    for x in [totals, *by_v.values(), *by_d.values()]:
        x["quantity"] = round(x["quantity"], 3)
    managers = [{**m, "vehicle_ids": sorted(m["vehicle_ids"])}
                for m in sorted(by_m.values(), key=lambda m: (m["manager_id"] is None, m["manager_id"] or 0))]
    return {
        "month": _ym(f), "open_days": len(open_days), "closed": _closing_out(_closing(f)),
        "totals": totals,
        "vehicles": sorted(({**finish_basis(x), **over.get(x["vehicle_id"], {})} for x in by_v.values()),
                           key=lambda x: x["plate_no"] or ""),
        "days": [by_d[k] for k in sorted(by_d)],
        "managers": managers,
    }


def close_month(month: str, memo: str | None, email: str) -> None:
    f, t = month_bounds(month)
    if t >= today():
        raise ValueError(f"{f.year}년 {f.month}월이 끝난 뒤({(t + timedelta(days=1)).isoformat()}부터) 마감할 수 있습니다")
    if _closing(f):
        raise ValueError("이미 마감된 달입니다")
    s = month_summary(month)
    if not s["totals"]["count"]:
        raise ValueError("이 달에 주유 기록이 없습니다 — 기록을 입력한 뒤 마감하세요")
    try:
        dash_db.insert_id("""
            INSERT INTO fuel_closings (close_month, total_amount, cost_amount, log_count, memo, closed_by)
            VALUES (:m, :tot, :cost, :n, :memo, :e) RETURNING id
        """, {"m": f, "tot": s["totals"]["total"], "cost": s["totals"]["cost"],
              "n": s["totals"]["count"], "memo": _text(memo), "e": email})
    except IntegrityError as exc:
        raise ValueError("이미 마감된 달입니다") from exc


def release_month(month: str, reason: str, email: str) -> None:
    reason = _text(reason)
    if not reason:
        raise ValueError("해제 사유를 입력하세요")
    f, _ = month_bounds(month)
    with get_dash_engine().begin() as conn:
        res = conn.execute(text("""
            UPDATE fuel_closings SET released_at = NOW(), released_by = :e, release_reason = :r
             WHERE close_month = :m AND released_at IS NULL
        """), {"e": email, "r": reason, "m": f})
    if res.rowcount == 0:
        raise ValueError("마감되지 않은 달입니다")


# ---------- 물류비용 ----------
def fuel_by_day(frm: date, to: date, is_open, deductible: set[int]
                ) -> tuple[dict[date, dict[int, int]], set[tuple[int, int]]]:
    """조회 기간이 걸친 달 전체의 주유 기록 → 달별·차량별 비용 → 그달 영업일 배분 → 조회 기간 날짜만.
    반환 = ({날짜: {차량: 금액}}, 마감된 (연, 월) 목록). is_open은 걸친 달 전체를 덮어야 함."""
    f0, _ = month_bounds(_ym(frm))
    _, t0 = month_bounds(_ym(to))
    p = {"f": f0, "t": t0}
    rows = dash_db.rows("""SELECT vehicle_id, fuel_date, total_amount, supply_amount FROM fuel_logs
        WHERE deleted_at IS NULL AND fuel_date BETWEEN :f AND :t""", p)
    closed = {(r["close_month"].year, r["close_month"].month) for r in dash_db.rows(
        "SELECT close_month FROM fuel_closings WHERE released_at IS NULL AND close_month BETWEEN :f AND :t", p)}
    per_month: dict[tuple[int, int], dict[int, int]] = {}
    for r in rows:
        vm = per_month.setdefault((r["fuel_date"].year, r["fuel_date"].month), {})
        vm[r["vehicle_id"]] = vm.get(r["vehicle_id"], 0) + log_cost(r, r["vehicle_id"] in deductible)
    out: dict[date, dict[int, int]] = {}
    for (y, m), by_vid in per_month.items():
        mf, mt = month_bounds(f"{y}-{m:02d}")
        opened = [x for x in days_between(mf, mt) if is_open(x)]
        for d, per in allocate_month(by_vid, opened, mf, mt).items():
            if frm <= d <= to:
                out[d] = per
    return out, closed
