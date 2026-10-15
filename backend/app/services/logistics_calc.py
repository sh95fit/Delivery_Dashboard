"""S3-P1 물류비 계산 순수 함수 (DB 없음 → 단위 테스트 대상).
기준: 정규직 월급·차량 기간 비용은 영업일로 나눔. 부가세 공제 차량은 부가세가 붙는 항목만 공급가액."""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Callable

from app.services.business_days import business_days, split_over
from app.services.cost_calc import allocate_period, days_incl
from app.services.worklog_calc import day_result, is_workday

# 부가세가 붙어 매입세액공제 대상이 되는 항목. 보험(면세)·자동차세·검사·감가·사고 자기부담금·기타는 입력 금액 그대로
VAT_CATS = frozenset({"repair", "maintenance", "tire", "towing", "parking", "wash", "lease", "fuel"})


def month_days(d: date) -> list[date]:
    """d가 속한 달의 모든 날짜."""
    first = d.replace(day=1)
    return [first + timedelta(days=i) for i in range(calendar.monthrange(d.year, d.month)[1])]


def supply_of(total: int) -> int:
    """합계(부가세 포함) → 공급가액, 원 단위 반올림. 예 144,000 → 130,909"""
    return (int(total) * 10 + 5) // 11


def cost_amount(amount: int, category: str, vat_deductible: bool) -> int:
    """물류비에 넣을 금액. 공제 차량 + 부가세 붙는 항목이면 공급가액, 그 외는 입력 금액 그대로."""
    amount = int(amount or 0)
    return supply_of(amount) if vat_deductible and category in VAT_CATS else amount


def monthly_day(amount: int, d: date, month_open: list[date] | None = None) -> int:
    """정규직 월급의 그날 몫 = 월급 ÷ 그 달 영업일 수. 휴무일 0원.
    나머지 원은 앞 영업일부터 1원씩 → 한 달 합계 = 월급. month_open 없으면 규칙(월~토, 일요일·공휴일 휴무)만 적용."""
    if month_open is None:
        md = month_days(d)
        month_open = business_days(md[0], md[-1])
    days = sorted(x for x in month_open if (x.year, x.month) == (d.year, d.month))
    if d not in days:
        return 0
    base, rem = divmod(int(amount), len(days))
    return base + (1 if days.index(d) < rem else 0)


def labor_day(rate: dict | None, log: dict | None, off: bool, d: date, today: date,
              month_open: list[date] | None = None) -> dict | None:
    """한 사람·하루 인건비 → {cost, ot_pay, paid_min, kind} 또는 None(비용 없음).
    kind = actual(근무 기록) / monthly(정규직 월급, 영업일 기준) / estimate(오늘 이후 계약 시간) / missing(지난 근무일 미입력 → 계약 시간)
    month_open = 그 달 영업일 목록. 휴무일에는 기록이 없으면 비용 없음, 기록이 있으면 실제 비용."""
    if rate is None:
        return None
    pt = rate.get("pay_type")
    if pt == "monthly":
        cost = monthly_day(int(rate["amount"]), d, month_open)
        return {"cost": cost, "ot_pay": 0, "paid_min": 0, "kind": "monthly"} if cost else None
    if pt != "hourly":
        return None
    is_open = d in month_open if month_open is not None else True
    if log is not None:
        kind = "actual"
    elif off or not is_open or not is_workday(rate, d) or rate.get("work_start") is None or rate.get("work_end") is None:
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


def period_shares(amount: int, start: date, end: date, is_open: Callable[[date], bool]) -> dict[date, int]:
    """기간 비용을 기간 안 영업일에 균등 배분 (나머지 원은 앞 날짜부터 → 합계 = amount).
    기간 안에 영업일이 하나도 없으면 달력 일수로 나눔 (금액이 사라지지 않게)."""
    all_days = [start + timedelta(days=i) for i in range(days_incl(start, end))]
    opened = [x for x in all_days if is_open(x)]
    return split_over(amount, opened or all_days)


def vehicle_costs(periods: list[dict], expenses: list[dict], deductible: set[int],
                  is_open: Callable[[date], bool], frm: date, to: date) -> dict[date, dict[int, int]]:
    """조회 기간의 날짜별·차량별 비용. 기간 비용 = 영업일 배분, 지출 = 입력한 날짜. 부가세 규칙은 cost_amount."""
    out: dict[date, dict[int, int]] = {}

    def put(d: date, vid: int, amt: int) -> None:
        if frm <= d <= to and amt:
            day = out.setdefault(d, {})
            day[vid] = day.get(vid, 0) + amt

    for p in periods:
        amt = cost_amount(p["amount"], p["category"], p["vehicle_id"] in deductible)
        for d, v in period_shares(amt, p["start_date"], p["end_date"], is_open).items():
            put(d, p["vehicle_id"], v)
    for e in expenses:
        put(e["expense_date"], e["vehicle_id"], cost_amount(e["amount"], e["category"], e["vehicle_id"] in deductible))
    return out


def vehicle_day(periods: list[dict], expenses: list[dict], d: date) -> dict[int, int]:
    """(이전 방식, 참고용) 그날 차량별 비용 = 기간 비용 달력 일할 + 그날 지출. 물류비 계산에는 vehicle_costs 사용."""
    out: dict[int, int] = {}
    for p in periods:
        v = allocate_period(p["amount"], p["start_date"], p["end_date"], d, d)
        if v:
            out[p["vehicle_id"]] = out.get(p["vehicle_id"], 0) + v
    for e in expenses:
        if e["expense_date"] == d:
            out[e["vehicle_id"]] = out.get(e["vehicle_id"], 0) + int(e["amount"])
    return out
