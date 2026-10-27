"""S3-P1 물류비 (계정 × 일자) — 매출 대비 비용 확인용. 지급·제출 금액이 아님 (근무표·급여와 별개).

금액 기준
- 매출 = 순매출(부가세 제외). 부가세는 회사 이익이 아니므로 뺀다.
- 비용 = 실제 부담액. 부가세 공제 차량은 부가세 붙는 항목만 공급가액, 그 외는 입력 금액 그대로.
- 정규직 월급, 차량 기간 비용은 영업일로 나눈다 (calendar_service).
규칙(순수 함수)은 logistics_calc 참고."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from app.services import calendar_service, dash_db
from app.services.cost_calc import days_incl, effective_on, latest_by
from app.services.day_aggregate import KST
from app.services.logistics_calc import labor_day, month_days, split_even, vehicle_costs
from app.services.manager_service import today
from app.services.route_fuel_service import route_fuel

MAX_DAYS = 366   # 1년(윤년 포함). 느리면 줄인다
logger = logging.getLogger("logistics")

COST_KEYS = ("labor", "labor_est", "ot_expected", "incentive", "extras", "vehicle", "fuel", "fuel_est")
REF_KEYS = ("ncp_fuel", "calc_fuel", "route_m", "route_ms", "cancel_loss")   # 참고 칸 — cost_total에 넣지 않음 (route_ms = 주행 시간, cancel_loss = S3-P2f 배송 취소로 받지 못한 매출, 순매출에서 이미 뺌)
NO_ACCOUNT = "계정 미지정"


def _blank() -> dict:
    return {"net_revenue": 0, **{k: 0 for k in COST_KEYS + REF_KEYS}}


def _d(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _group(rows: list[dict], key: str) -> dict:
    out: dict = {}
    for r in rows:
        out.setdefault(r[key], []).append(r)
    return out


def _finish(x: dict) -> dict:
    cost = sum(int(x[k]) for k in COST_KEYS)
    rev = int(x["net_revenue"])
    return {**x, "cost_total": cost, "profit": rev - cost,
            "cost_ratio": round(cost * 100 / rev, 1) if rev > 0 else None,
            "route_km": round(int(x.get("route_m") or 0) / 1000, 1),
            "route_min": round(int(x.get("route_ms") or 0) / 60000)}


def _timed(timing: dict, key: str, fn):
    s = time.perf_counter()
    try:
        return fn()
    finally:
        timing[key] = round(time.perf_counter() - s, 2)


def cost_view(frm: date, to: date) -> dict:
    if to < frm:
        raise ValueError("조회 종료일이 시작일보다 빠릅니다")
    if days_incl(frm, to) > MAX_DAYS:
        raise ValueError(f"조회 기간은 {MAX_DAYS}일 이내로 지정하세요")
    from app.services.incentive_service import _build, _managers   # 함수 안 import = 순환 import 방지
    from app.services.revenue_service import _views

    t = today()
    now = datetime.now(KST)
    started = time.perf_counter()
    timing: dict[str, float] = {}
    days = [frm + timedelta(days=i) for i in range(days_incl(frm, to))]
    cells: dict[tuple[date, int | None], dict] = {}
    names: dict[int | None, str] = {}
    issues: list[dict] = []

    def cell(d: date, mid: int | None) -> dict:
        return cells.setdefault((d, mid), _blank())

    def add(level: str, msg: str) -> None:
        issues.append({"level": level, "msg": msg})

    # 운영 DB 조회(매출·인센티브)는 오래 걸리므로 동시에 띄워 두고, 기다리는 동안 대시보드 DB 계산을 한다
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_rev = ex.submit(_timed, timing, "revenue", lambda: _views(frm, to, now))
        f_inc = ex.submit(_timed, timing, "incentive", lambda: _build(frm, to, detail=False))

        # ---------- 영업일 ----------
        s = time.perf_counter()
        p = {"a": frm, "b": to}
        periods = dash_db.rows("""SELECT vehicle_id, category, amount, start_date, end_date FROM vehicle_period_costs
            WHERE deleted_at IS NULL AND start_date <= :b AND end_date >= :a""", p)
        lo = min([frm.replace(day=1)] + [r["start_date"] for r in periods])
        hi = max([month_days(to)[-1]] + [r["end_date"] for r in periods])
        is_open = calendar_service.open_checker(lo, hi)
        month_open: dict[tuple[int, int], list[date]] = {}

        def open_in_month(d: date) -> list[date]:
            k = (d.year, d.month)
            if k not in month_open:
                month_open[k] = [x for x in month_days(d) if is_open(x)]
            return month_open[k]

        # ---------- 인건비 ----------
        workers = dash_db.rows("""SELECT id, name, active, end_date, last_pay_full, last_pay_amount
            FROM workers WHERE deleted_at IS NULL""")
        rates = _group(dash_db.rows("SELECT * FROM worker_pay_rates WHERE deleted_at IS NULL"), "worker_id")
        accs = _group(dash_db.rows(
            "SELECT worker_id, manager_id, start_date FROM worker_accounts WHERE deleted_at IS NULL"), "worker_id")
        logs = {(r["worker_id"], r["work_date"]): r for r in dash_db.rows(
            "SELECT * FROM work_logs WHERE deleted_at IS NULL AND work_date BETWEEN :a AND :b", p)}
        offs = {(r["worker_id"], r["work_date"]) for r in dash_db.rows(
            "SELECT worker_id, work_date FROM work_offs WHERE deleted_at IS NULL AND work_date BETWEEN :a AND :b", p)}
        owned: dict[tuple[int, date], int] = {}
        for o in dash_db.rows("""SELECT worker_id, work_date, manager_id FROM incentive_owners
                                 WHERE deleted_at IS NULL AND work_date BETWEEN :a AND :b ORDER BY id""", p):
            owned.setdefault((o["worker_id"], o["work_date"]), int(o["manager_id"]))
        missing: dict[str, list[str]] = {}
        no_acc: dict[str, int] = {}
        nocontract: set[str] = set()
        no_end: set[str] = set()
        for w in workers:
            wid, rs = w["id"], rates.get(w["id"], [])
            end = w.get("end_date")                     # [S2-P0c] 퇴사일까지는 활성 인력과 똑같이 계산
            last_pay = w.get("last_pay_amount") if w.get("last_pay_full") is False else None
            if not w["active"] and end is None:
                no_end.add(w["name"])
            for d in days:
                lg = logs.get((wid, d))
                if lg is None and not w["active"] and end is None:
                    continue                            # 퇴사일 없는 예전 비활성 인력: 근무 기록 있는 날만
                res = labor_day(effective_on(rs, d, "effective_from"), lg, (wid, d) in offs, d, t, open_in_month(d),
                                end=end, last_pay=last_pay)
                if res is None:
                    if lg is not None and effective_on(rs, d, "effective_from") is None:
                        nocontract.add(w["name"])
                    continue
                a = effective_on(accs.get(wid, []), d, "start_date")
                # 인센티브와 같은 순서: 담당 지정 → 근무 기록의 그날 계정 → 고정 계정
                mid = owned.get((wid, d)) or (lg or {}).get("manager_id") or (a["manager_id"] if a else None)
                c = cell(d, mid)
                c["labor" if res["kind"] in ("actual", "monthly") else "labor_est"] += res["cost"]
                c["ot_expected"] += res["ot_pay"]
                if res["kind"] == "missing":
                    missing.setdefault(w["name"], []).append(f"{d.month}/{d.day}")
                if mid is None:
                    no_acc[w["name"]] = no_acc.get(w["name"], 0) + res["cost"]
        for name, ds in missing.items():
            more = f" 외 {len(ds) - 5}일" if len(ds) > 5 else ""
            add("warn", f"{name}: 근무 기록 미입력 {len(ds)}일({', '.join(ds[:5])}{more}) — 계약 시간으로 예상 계산")
        for name, amt in no_acc.items():
            add("warn", f"{name}: 그날 계정·고정 계정이 없어 인건비 {amt:,}원이 '{NO_ACCOUNT}'로 들어감")
        for name in sorted(nocontract):
            add("warn", f"{name}: 계약 없는 날 근무 기록이 있어 그날 인건비 0원 — 계약 시작일 확인")
        for name in sorted(no_end):
            add("warn", f"{name}: 비활성인데 퇴사일이 없어 근무 기록 있는 날만 계산 — 인력 화면에서 퇴사일을 넣으면 그 전 기간 인건비가 다시 잡힘")            
        if not any(r.get("pay_type") == "monthly" for rs in rates.values() for r in rs):
            add("info", "월급(정규직)으로 등록된 인력이 없어 정규직 인건비가 0원 — 인력 화면에서 정규직 등록 후 계약을 '월급'으로 입력")
        timing["labor"] = round(time.perf_counter() - s, 2)

        # ---------- 차량비 (그날 그 차량을 배정받은 계정이 나눠 가짐) ----------
        s = time.perf_counter()
        expenses = dash_db.rows("""SELECT vehicle_id, category, expense_date, amount FROM vehicle_expenses
            WHERE deleted_at IS NULL AND expense_date BETWEEN :a AND :b""", p)
        deductible = {r["id"] for r in dash_db.rows("SELECT id FROM vehicles WHERE vat_deductible")}
        assigns = dash_db.rows(
            "SELECT manager_id, vehicle_id, start_date FROM vehicle_assignments WHERE deleted_at IS NULL")
        vcost = vehicle_costs(periods, expenses, deductible, is_open, frm, to)
        loose = 0
        for d in days:
            day_cost = vcost.get(d)
            if not day_cost:
                continue
            users: dict[int, list[int]] = {}
            for mid, a in latest_by(assigns, "manager_id", "start_date", d).items():
                if a["vehicle_id"]:
                    users.setdefault(a["vehicle_id"], []).append(mid)
            for vid, amt in day_cost.items():
                if not users.get(vid):
                    cell(d, None)["vehicle"] += amt
                    loose += amt
                    continue
                for mid, share in split_even(amt, users[vid]).items():
                    cell(d, mid)["vehicle"] += share
                    
        # ---------- 유류비 (그달 영업일 배분 → 그날 차량 배정 계정에 균분. 마감 = 확정, 마감 전 = 입력분 예상) ----------
        from app.services.fuel_log_service import fuel_by_day   # 함수 안 import = 순환 import 방지
        fuel_days, fuel_closed = fuel_by_day(frm, to, is_open, deductible)
        fuel_open: set[tuple[int, int]] = set()
        for d, per_vid in fuel_days.items():
            key = "fuel" if (d.year, d.month) in fuel_closed else "fuel_est"
            if key == "fuel_est":
                fuel_open.add((d.year, d.month))
            users = {}
            for mid, a in latest_by(assigns, "manager_id", "start_date", d).items():
                if a["vehicle_id"]:
                    users.setdefault(a["vehicle_id"], []).append(mid)
            for vid, amt in per_vid.items():
                if not users.get(vid):
                    cell(d, None)[key] += amt
                    loose += amt
                    continue
                for mid, share in split_even(amt, users[vid]).items():
                    cell(d, mid)[key] += share
        if fuel_open:
            months = ", ".join(f"{y}-{m:02d}" for y, m in sorted(fuel_open))
            add("info", f"유류비 미마감 {months} — 지금까지 입력한 주유 기록으로 예상 계산 (월 마감 후 확정)")
        if loose:
            add("info", f"배정 계정이 없는 차량 비용 {loose:,}원은 '{NO_ACCOUNT}'로 들어감")

        timing["vehicle"] = round(time.perf_counter() - s, 2)

        # ---------- 참고: NCP 예상 유류비 · 직접 계산 (S3-P2b, 합계에 넣지 않음) ----------
        s = time.perf_counter()
        rf, rf_notes = route_fuel(frm, to, assigns)
        for (d, mid), x in rf.items():
            c = cell(d, mid)
            c["route_m"] += x["route_m"]
            c["ncp_fuel"] += x["ncp"]
            c["calc_fuel"] += x["calc"]
            c["route_ms"] += x["route_ms"]            
        for n in rf_notes:
            add("info", n)
        timing["route"] = round(time.perf_counter() - s, 2)        
        rev_views = f_rev.result()
        inc_rows = f_inc.result()

    # ---------- 매출 (하루 카드와 같은 계산) ----------
    for v in rev_views:
        d = _d(v["date"])
        for m in v.get("managers") or []:
            mid = m.get("manager_id")
            cell(d, mid)["net_revenue"] += int(m.get("net_revenue") or 0)            
            cell(d, mid)["cancel_loss"] += int(m.get("cancel_loss") or 0)
            if m.get("manager_name"):
                names[mid] = m["manager_name"]

    # ---------- 데일리 인센티브 · 특수 수당 (인센티브 화면 계산 그대로) ----------
    pending = 0
    for (d, mid), r in inc_rows.items():
        c = cell(d, mid)
        c["incentive"] += int(r["payable"] or 0)
        c["extras"] += int(r["extras"])
        if r["status"] == "need_accounts" and int(r.get("stops") or 0) > 0 and d <= t:
            pending += 1
    if pending:
        add("warn", f"고객사 수 미입력 {pending}건(계정×일)은 데일리 인센티브 0원으로 계산됨 — 인센티브 > 일자별 입력")

    # ---------- 조립 ----------
    mgrs = _managers()
    accounts: dict[int | None, dict] = {}
    by_day = {d: _blank() for d in days}
    for (d, mid), c in cells.items():
        acc = accounts.setdefault(mid, {"manager_id": mid, **_blank()})
        for k, v in c.items():
            acc[k] += v
            by_day[d][k] += v
    rows = []
    for mid, acc in accounts.items():
        name = NO_ACCOUNT if mid is None else ((mgrs.get(mid) or {}).get("name") or names.get(mid) or f"계정 {mid}")
        rows.append(_finish({**acc, "manager_name": name}))
    rows.sort(key=lambda x: (x["manager_id"] is None, -x["net_revenue"]))
    totals = _finish({k: sum(r[k] for r in rows) for k in ("net_revenue",) + COST_KEYS + REF_KEYS})
    if totals["cancel_loss"]:
        add("info", f"배송 취소로 받지 못한 매출 {totals['cancel_loss']:,}원 — 순매출에서 이미 빠져 이익에 반영됨 (물류비 합계에는 넣지 않음)")    
    if totals["labor_est"]:
        add("info", f"인건비 중 {totals['labor_est']:,}원은 근무 기록이 없는 날의 예상 금액")
    timing["total"] = round(time.perf_counter() - started, 2)
    logger.info("cost_view %s~%s %d일 %s", frm, to, len(days), timing)
    return {"from": frm.isoformat(), "to": to.isoformat(), "days": len(days), "today": t.isoformat(),
            "open_days": sum(1 for d in days if is_open(d)), "timing": timing,
            "accounts": rows,
            "by_day": [{"date": d.isoformat(), **_finish(v)} for d, v in sorted(by_day.items())],
            "totals": totals, "issues": issues}
