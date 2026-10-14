"""S3-P1 물류비 (계정 × 일자) — 매출 대비 비용 확인용. 지급·제출 금액이 아님 (근무표·급여와 별개).
규칙은 logistics_calc 참고. 금액은 모두 공급가(부가세 제외) — 순매출이 VAT 제외이므로 같은 기준."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from app.services import dash_db
from app.services.cost_calc import days_incl, effective_on, latest_by
from app.services.day_aggregate import KST
from app.services.logistics_calc import labor_day, split_even, vehicle_day
from app.services.manager_service import today

MAX_DAYS = 62
COST_KEYS = ("labor", "labor_est", "ot_expected", "incentive", "extras", "vehicle")
NO_ACCOUNT = "계정 미지정"


def _blank() -> dict:
    return {"net_revenue": 0, **{k: 0 for k in COST_KEYS}}


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
            "cost_ratio": round(cost * 100 / rev, 1) if rev > 0 else None}


def cost_view(frm: date, to: date) -> dict:
    if to < frm:
        raise ValueError("조회 종료일이 시작일보다 빠릅니다")
    if days_incl(frm, to) > MAX_DAYS:
        raise ValueError(f"조회 기간은 {MAX_DAYS}일 이내로 지정하세요")
    from app.services.incentive_service import _build, _managers   # 함수 안 import = 순환 import 방지
    from app.services.revenue_service import _views

    t = today()
    days = [frm + timedelta(days=i) for i in range(days_incl(frm, to))]
    cells: dict[tuple[date, int | None], dict] = {}
    names: dict[int | None, str] = {}
    issues: list[dict] = []

    def cell(d: date, mid: int | None) -> dict:
        return cells.setdefault((d, mid), _blank())

    def add(level: str, msg: str) -> None:
        issues.append({"level": level, "msg": msg})

    # 매출 (하루 카드와 같은 계산)
    for v in _views(frm, to, datetime.now(KST)):
        d = _d(v["date"])
        for m in v.get("managers") or []:
            mid = m.get("manager_id")
            cell(d, mid)["net_revenue"] += int(m.get("net_revenue") or 0)
            if m.get("manager_name"):
                names[mid] = m["manager_name"]

    # 데일리 인센티브 · 특수 수당 (인센티브 화면 계산 그대로)
    pending = 0
    for (d, mid), r in _build(frm, to, detail=False).items():
        c = cell(d, mid)
        c["incentive"] += int(r["payable"] or 0)
        c["extras"] += int(r["extras"])
        if r["status"] == "need_accounts" and int(r.get("stops") or 0) > 0 and d <= t:
            pending += 1
    if pending:
        add("warn", f"고객사 수 미입력 {pending}건(계정×일)은 데일리 인센티브 0원으로 계산됨 — 인센티브 > 일자별 입력")

    # 인건비
    p = {"a": frm, "b": to}
    workers = dash_db.rows("SELECT id, name, active FROM workers WHERE deleted_at IS NULL")
    rates = _group(dash_db.rows("SELECT * FROM worker_pay_rates WHERE deleted_at IS NULL"), "worker_id")
    accs = _group(dash_db.rows("SELECT worker_id, manager_id, start_date FROM worker_accounts WHERE deleted_at IS NULL"),
                  "worker_id")
    logs = {(r["worker_id"], r["work_date"]): r for r in dash_db.rows(
        "SELECT * FROM work_logs WHERE deleted_at IS NULL AND work_date BETWEEN :a AND :b", p)}
    offs = {(r["worker_id"], r["work_date"]) for r in dash_db.rows(
        "SELECT worker_id, work_date FROM work_offs WHERE deleted_at IS NULL AND work_date BETWEEN :a AND :b", p)}
    missing: dict[str, list[str]] = {}
    no_acc: dict[str, int] = {}
    nocontract: set[str] = set()
    for w in workers:
        wid, rs = w["id"], rates.get(w["id"], [])
        for d in days:
            lg = logs.get((wid, d))
            if lg is None and not w["active"]:
                continue
            res = labor_day(effective_on(rs, d, "effective_from"), lg, (wid, d) in offs, d, t)
            if res is None:
                if lg is not None:
                    nocontract.add(w["name"])
                continue
            a = effective_on(accs.get(wid, []), d, "start_date")
            mid = (lg or {}).get("manager_id") or (a["manager_id"] if a else None)
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

    # 차량비 (그날 그 차량을 배정받은 계정이 나눠 가짐)
    periods = dash_db.rows("""SELECT vehicle_id, amount, start_date, end_date FROM vehicle_period_costs
        WHERE deleted_at IS NULL AND start_date <= :b AND end_date >= :a""", p)
    expenses = dash_db.rows("""SELECT vehicle_id, expense_date, amount FROM vehicle_expenses
        WHERE deleted_at IS NULL AND expense_date BETWEEN :a AND :b""", p)
    assigns = dash_db.rows("SELECT manager_id, vehicle_id, start_date FROM vehicle_assignments WHERE deleted_at IS NULL")
    loose = 0
    for d in days:
        users: dict[int, list[int]] = {}
        for mid, a in latest_by(assigns, "manager_id", "start_date", d).items():
            if a["vehicle_id"]:
                users.setdefault(a["vehicle_id"], []).append(mid)
        for vid, amt in vehicle_day(periods, expenses, d).items():
            if not users.get(vid):
                cell(d, None)["vehicle"] += amt
                loose += amt
                continue
            for mid, share in split_even(amt, users[vid]).items():
                cell(d, mid)["vehicle"] += share
    if loose:
        add("info", f"배정 계정이 없는 차량 비용 {loose:,}원은 '{NO_ACCOUNT}'로 들어감")

    # 조립
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
    totals = _finish({k: sum(r[k] for r in rows) for k in ("net_revenue",) + COST_KEYS})
    if totals["labor_est"]:
        add("info", f"인건비 중 {totals['labor_est']:,}원은 근무 기록이 없는 날의 예상 금액")
    return {"from": frm.isoformat(), "to": to.isoformat(), "days": len(days), "today": t.isoformat(),
            "accounts": rows,
            "by_day": [{"date": d.isoformat(), **_finish(v)} for d, v in sorted(by_day.items())],
            "totals": totals, "issues": issues}
