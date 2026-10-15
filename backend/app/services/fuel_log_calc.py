"""S3-P1b-2b 주유 기록 계산 순수 함수 (DB 없음 → 단위 테스트 대상).

- 공급가액·부가세를 비우면 합계 ÷ 1.1 (원 단위 반올림, 144,000 → 130,909 + 13,091)
- 비용 = 부가세 공제 차량은 공급가액, 불공제 차량은 합계
- 그달 차량별 금액을 그달 영업일로 나눔 (나머지 원은 앞 날짜부터). 영업일이 없으면 달력 일수
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from app.services.business_days import split_over
from app.services.logistics_calc import supply_of


def month_bounds(month: str) -> tuple[date, date]:
    """'2026-09' → (2026-09-01, 2026-09-30)."""
    try:
        y, m = (int(x) for x in str(month).split("-")[:2])
        first = date(y, m, 1)
    except (ValueError, TypeError) as exc:
        raise ValueError("월은 2026-09 형식으로 입력하세요") from exc
    return first, first.replace(day=calendar.monthrange(y, m)[1])


def days_between(first: date, last: date) -> list[date]:
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def amounts(total, supply=None, vat=None) -> tuple[int, int, int]:
    """(합계, 공급가액, 부가세). 둘 다 비우면 자동, 하나만 있으면 나머지 = 합계 - 입력값."""
    total = int(total or 0)
    if total <= 0:
        raise ValueError("합계 금액을 입력하세요")
    if supply is None and vat is None:
        supply = supply_of(total)
        vat = total - supply
    elif vat is None:
        supply = int(supply)
        vat = total - supply
    elif supply is None:
        vat = int(vat)
        supply = total - vat
    else:
        supply, vat = int(supply), int(vat)
        if supply + vat != total:
            raise ValueError(f"공급가액 {supply:,}원 + 부가세 {vat:,}원 = {supply + vat:,}원이 합계 {total:,}원과 다릅니다")
    if supply < 0 or vat < 0:
        raise ValueError("공급가액·부가세는 합계보다 클 수 없습니다")
    return total, supply, vat


def log_cost(row: dict, deductible: bool) -> int:
    """물류비에 넣을 금액. 공제 차량 = 공급가액, 불공제 차량 = 합계."""
    return int(row["supply_amount"]) if deductible else int(row["total_amount"])


def allocate_month(amount_by_vehicle: dict[int, int], open_days: list[date],
                   first: date, last: date) -> dict[date, dict[int, int]]:
    """차량별 한 달 금액 → {날짜: {차량: 금액}}. 차량마다 합계가 그대로 유지됨."""
    days = sorted(open_days) or days_between(first, last)
    out: dict[date, dict[int, int]] = {}
    for vid, amt in amount_by_vehicle.items():
        if not amt:
            continue
        for d, v in split_over(int(amt), days).items():
            if v:
                day = out.setdefault(d, {})
                day[vid] = day.get(vid, 0) + v
    return out
