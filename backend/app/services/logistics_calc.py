"""S3-P1 물류비 계산 순수 함수 (DB 없음 → 단위 테스트 대상)."""
from __future__ import annotations

import calendar
from datetime import date

from app.services.cost_calc import allocate_period
from app.services.worklog_calc import day_result, is_workday


def monthly_day(amount: int, d: date) -> int:
    """정규직 월급의 그날 몫 (달력 일수로 나눔, 나머지 원은 앞쪽 날짜부터 → 한 달 합계 = 월급)."""
    first = d.replace(day=1)
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    return allocate_period(int(amount), first, last, d, d)


def labor_day(rate: dict | None, log: dict | None, off: bool, d: date, today: date) -> dict | None:
    """한 사람·하루 인건비 → {cost, ot_pay, paid_min, kind} 또는 None(비용 없음).
    kind = actual(근무 기록) / monthly(정규직 월급 일할) / estimate(오늘 이후 계약 시간) / missing(지난 근무 요일 미입력 → 계약 시간)"""
    if rate is None:
        return None
    pt = rate.get("pay_type")
    if pt == "monthly":
        return {"cost": monthly_day(int(rate["amount"]), d), "ot_pay": 0, "paid_min": 0, "kind": "monthly"}
    if pt != "hourly":
        return None
    if log is not None:
        kind = "actual"
    elif off or not is_workday(rate, d) or rate.get("work_start") is None or rate.get("work_end") is None:
        return None
    else:
        kind = "missing" if d < today else "estimate"
        log = {"clock_in": rate["work_start"], "clock_out": rate["work_end"], "break_min": None}
    r = day_result(log, rate)
    return {"cost": (int(r["paid"]) * int(rate["amount"]) + 30) // 60, "ot_pay": int(r["ot_pay"]),
            "paid_min": int(r["paid"]), "kind": kind}


def split_even(amount: int, keys: list) -> dict:
    """금액을 keys에 똑같이 나눔. 나머지 원은 정렬 순서 앞쪽부터 1원씩 → 합계 = amount."""
    ks = sorted(set(keys))
    base, rem = divmod(int(amount), len(ks))
    return {k: base + (1 if i < rem else 0) for i, k in enumerate(ks)}


def vehicle_day(periods: list[dict], expenses: list[dict], d: date) -> dict[int, int]:
    """그날 차량별 비용 = 기간 비용 일할 + 그날 지출."""
    out: dict[int, int] = {}
    for p in periods:
        v = allocate_period(p["amount"], p["start_date"], p["end_date"], d, d)
        if v:
            out[p["vehicle_id"]] = out.get(p["vehicle_id"], 0) + v
    for e in expenses:
        if e["expense_date"] == d:
            out[e["vehicle_id"]] = out.get(e["vehicle_id"], 0) + int(e["amount"])
    return out
