from datetime import date, time

from app.services.business_days import business_days
from app.services.logistics_calc import (cost_amount, labor_day, monthly_day, period_shares, split_even,
                                         supply_of, vehicle_costs, vehicle_day)

HOURLY = {"pay_type": "hourly", "amount": 16000, "work_start": time(7), "work_end": time(12, 30),
          "break_min": 0, "break_paid": True, "ot_unit_min": 0, "ot_unit_amount": 0, "work_days": 31}
TODAY = date(2026, 10, 13)   # 화요일
SEP = business_days(date(2026, 9, 1), date(2026, 9, 30))
OCT = business_days(date(2026, 10, 1), date(2026, 10, 31))
LOG = {"clock_in": time(7), "clock_out": time(13), "break_min": None}


def test_calendar_counts():
    assert len(SEP) == 23 and len(OCT) == 25
    assert date(2026, 10, 5) in OCT          # 개천절 대체공휴일 → 영업
    assert date(2026, 10, 9) not in OCT      # 한글날 휴무


def test_labor_actual_uses_log():
    r = labor_day(HOURLY, LOG, False, date(2026, 10, 12), TODAY)
    assert r == {"cost": 96_000, "ot_pay": 0, "paid_min": 360, "kind": "actual"}


def test_labor_without_log_estimates_contract():
    assert labor_day(HOURLY, None, False, date(2026, 10, 12), TODAY)["kind"] == "missing"
    r = labor_day(HOURLY, None, False, date(2026, 10, 14), TODAY)
    assert r["kind"] == "estimate" and r["cost"] == 88_000
    assert labor_day(HOURLY, None, True, date(2026, 10, 12), TODAY) is None      # 휴무 등록
    assert labor_day(HOURLY, None, False, date(2026, 10, 17), TODAY) is None     # 토요일 (월~금 계약)


def test_labor_closed_day():
    assert labor_day(HOURLY, None, False, date(2026, 10, 9), TODAY, OCT) is None             # 한글날, 기록 없음 → 예상 안 함
    assert labor_day(HOURLY, LOG, False, date(2026, 10, 9), TODAY, OCT)["kind"] == "actual"  # 일했으면 비용


def test_monthly_by_business_days():
    rate = {"pay_type": "monthly", "amount": 3_100_000}
    assert monthly_day(3_100_000, date(2026, 10, 5), OCT) == 124_000            # 3,100,000 ÷ 25
    assert monthly_day(3_100_000, date(2026, 10, 5)) == 124_000                 # 예외 지정 없이 규칙만
    assert labor_day(rate, None, False, date(2026, 10, 4), TODAY, OCT) is None   # 일요일
    assert labor_day(rate, None, False, date(2026, 10, 9), TODAY, OCT) is None   # 한글날
    odd = {"pay_type": "monthly", "amount": 3_100_001}
    days = [date(2026, 10, d) for d in range(1, 32)]
    assert sum((labor_day(odd, None, False, d, TODAY, OCT) or {"cost": 0})["cost"] for d in days) == 3_100_001


def test_period_shares_business_days():
    s = period_shares(2300, date(2026, 9, 1), date(2026, 9, 30), lambda d: d in SEP)
    assert len(s) == 23 and set(s.values()) == {100} and date(2026, 9, 6) not in s
    assert period_shares(500, date(2026, 9, 6), date(2026, 9, 6), lambda d: d in SEP) == {date(2026, 9, 6): 500}


def test_vat_rules():
    assert supply_of(144_000) == 130_909
    assert cost_amount(144_000, "repair", True) == 130_909
    assert cost_amount(144_000, "insurance", True) == 144_000     # 보험은 면세 → 그대로
    assert cost_amount(144_000, "repair", False) == 144_000       # 불공제 차량 → 합계


def test_vehicle_costs():
    periods = [{"vehicle_id": 1, "category": "lease", "amount": 253_000,
                "start_date": date(2026, 9, 1), "end_date": date(2026, 9, 30)}]
    expenses = [{"vehicle_id": 2, "category": "repair", "amount": 55_000, "expense_date": date(2026, 9, 6)}]
    out = vehicle_costs(periods, expenses, {1}, lambda d: d in SEP, date(2026, 9, 1), date(2026, 9, 30))
    assert out[date(2026, 9, 1)] == {1: 10_000}                   # 230,000 ÷ 23
    assert out[date(2026, 9, 6)] == {2: 55_000}                   # 지출은 입력한 날짜 그대로
    assert sum(v.get(1, 0) for v in out.values()) == 230_000


def test_split_and_vehicle_day():
    assert split_even(11, [3, 1, 2]) == {1: 4, 2: 4, 3: 3}
    periods = [{"vehicle_id": 1, "amount": 3100, "start_date": date(2026, 10, 1), "end_date": date(2026, 10, 31)}]
    expenses = [{"vehicle_id": 1, "expense_date": date(2026, 10, 5), "amount": 5000}]
    assert vehicle_day(periods, expenses, date(2026, 10, 5)) == {1: 5100}
