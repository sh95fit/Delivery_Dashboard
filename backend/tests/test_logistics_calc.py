from datetime import date, time

from app.services.logistics_calc import labor_day, monthly_day, split_even, vehicle_day

HOURLY = {"pay_type": "hourly", "amount": 16000, "work_start": time(7), "work_end": time(12, 30),
          "break_min": 0, "break_paid": True, "ot_unit_min": 0, "ot_unit_amount": 0, "work_days": 31}
TODAY = date(2026, 10, 13)   # 화요일


def test_labor_actual_uses_log():
    r = labor_day(HOURLY, {"clock_in": time(7), "clock_out": time(13), "break_min": None}, False, date(2026, 10, 12), TODAY)
    assert r == {"cost": 96_000, "ot_pay": 0, "paid_min": 360, "kind": "actual"}


def test_labor_without_log_estimates_contract():
    assert labor_day(HOURLY, None, False, date(2026, 10, 12), TODAY)["kind"] == "missing"     # 지난 근무일
    r = labor_day(HOURLY, None, False, date(2026, 10, 14), TODAY)
    assert r["kind"] == "estimate" and r["cost"] == 88_000                                     # 5시간 30분
    assert labor_day(HOURLY, None, True, date(2026, 10, 12), TODAY) is None                    # 휴무
    assert labor_day(HOURLY, None, False, date(2026, 10, 17), TODAY) is None                   # 토요일 (월~금 계약)


def test_monthly_split_sums_to_salary():
    rate = {"pay_type": "monthly", "amount": 3_100_001}
    days = [date(2026, 10, d) for d in range(1, 32)]
    assert sum(labor_day(rate, None, False, d, TODAY)["cost"] for d in days) == 3_100_001
    assert monthly_day(3_100_000, date(2026, 10, 5)) == 100_000


def test_split_and_vehicle_day():
    assert split_even(11, [3, 1, 2]) == {1: 4, 2: 4, 3: 3}
    periods = [{"vehicle_id": 1, "amount": 3100, "start_date": date(2026, 10, 1), "end_date": date(2026, 10, 31)}]
    expenses = [{"vehicle_id": 1, "expense_date": date(2026, 10, 5), "amount": 5000}]
    assert vehicle_day(periods, expenses, date(2026, 10, 5)) == {1: 5100}
    assert vehicle_day(periods, expenses, date(2026, 10, 6)) == {1: 100}
