"""S2-P0c 퇴사일 · 정규직 마지막 달 급여 (logistics_calc.labor_day)."""
from datetime import date

from app.services.logistics_calc import labor_day

RATE_M = {"pay_type": "monthly", "amount": 3_000_000}
OCT = [date(2026, 10, d) for d in range(1, 32)]
OPEN = [d for d in OCT if d.weekday() != 6]      # 테스트용: 일요일만 휴무
TODAY = date(2026, 10, 21)
END = date(2026, 10, 15)


def _sum(**kw) -> int:
    return sum((labor_day(RATE_M, None, False, d, TODAY, OPEN, **kw) or {}).get("cost", 0) for d in OCT)


def test_no_end_full_month():
    assert _sum() == 3_000_000


def test_end_full_pay_until_end():
    assert _sum(end=END) == 3_000_000
    assert labor_day(RATE_M, None, False, date(2026, 10, 16), TODAY, OPEN, end=END) is None


def test_end_last_pay_amount():
    assert _sum(end=END, last_pay=1_000_000) == 1_000_000


def test_before_end_month_unchanged():
    sep = [date(2026, 9, d) for d in range(1, 31)]
    sep_open = [d for d in sep if d.weekday() != 6]
    total = sum((labor_day(RATE_M, None, False, d, TODAY, sep_open, end=END, last_pay=1) or {}).get("cost", 0) for d in sep)
    assert total == 3_000_000


def test_hourly_after_end_none():
    rate = {"pay_type": "hourly", "amount": 10_000}
    assert labor_day(rate, None, False, date(2026, 10, 20), TODAY, OPEN, end=END) is None
