from datetime import time
import pytest

from app.services.worker_calc import day_calc, month_pay, pay_total, recognized_in, resolve_accounts, check_rate

EARLY = dict(break_min=0, break_paid=True, work_start=time(7), work_end=time(12, 30), ot_unit_min=30, ot_unit_amount=5000)
LATE = {**EARLY, "work_end": time(13, 30)}   # 김도연 9/8부터


def test_recognized_in():
    assert recognized_in(time(6, 41), time(7)) == time(7)
    assert recognized_in(time(7, 5), time(7)) == time(7, 5)
    assert recognized_in(time(6, 41), None) == time(6, 41)


def test_day_overtime_outside_contract():
    d = day_calc(time(7), time(13, 13), **EARLY)             # 9/1
    assert (d["paid"], d["ot"], d["ot_pay"]) == (373, 43, 5000)
    d = day_calc(time(7), time(14, 2), **LATE)               # 9/21
    assert (d["paid"], d["ot"], d["ot_pay"]) == (422, 32, 5000)
    d = day_calc(time(6, 30), time(13, 23), **LATE)          # 9/16 조기 출근(인정)
    assert (d["ot"], d["ot_pay"]) == (30, 5000)
    d = day_calc(time(7), time(13, 36), **LATE)              # 9/15 단위 미만
    assert (d["ot"], d["ot_pay"]) == (6, 0)
    d = day_calc(time(7), time(13, 50), **{**LATE, "ot_unit_min": 0})
    assert (d["ot"], d["ot_pay"]) == (20, 0)


def test_unpaid_break():
    d = day_calc(time(7), time(13, 30), **{**LATE, "break_min": 30, "break_paid": False})
    assert (d["paid"], d["ot"]) == (360, 0)


def test_base_includes_overtime_and_matches_sheet():
    assert month_pay([{"paid": 126 * 60 + 34, "ot": 271, "rate": 16000, "ot_pay": 35000}])["base"] == 2_025_067
    assert month_pay([{"paid": 139 * 60 + 5, "ot": 0, "rate": 27500, "ot_pay": 0}])["base"] == 3_824_792


def test_overtime_allowance_is_added_on_top():
    m = month_pay([
        {"paid": 422, "ot": 32, "rate": 16000, "ot_pay": 5000},
        {"paid": 390, "ot": 0, "rate": 16000, "ot_pay": 0},
    ])
    assert (m["base"], m["ot_min"], m["ot_allow"]) == (216_533, 32, 5000)   # 기본급에 초과 32분 포함
    assert pay_total(m["base"], m["ot_allow"], 0, False)["total"] == 221_533


def test_rate_change_mid_month():
    assert month_pay([{"paid": 600, "ot": 0, "rate": 15000, "ot_pay": 0},
                      {"paid": 600, "ot": 0, "rate": 16000, "ot_pay": 0}])["base"] == 310_000


def test_vat():
    assert pay_total(4_218_500, 0, 0, True) == {"supply": 4_218_500, "vat": 421_850, "total": 4_640_350}   # 조영진
    assert pay_total(1_732_042, 0, 18_410, True)["total"] == 1_925_497                                     # 최정길
    assert pay_total(4_218_500, 10_000, 0, True)["total"] == 4_651_350                                     # 초과수당도 부가세 대상
    assert pay_total(2_025_067, 0, 0, False)["vat"] == 0


def test_resolve_accounts():
    fixed = {101: 1, 102: 2, 103: 3}
    assert resolve_accounts(fixed, {}) == {1: 101, 2: 102, 3: 103}
    assert resolve_accounts(fixed, {2: 101}) == {2: 101, 3: 103}
    assert resolve_accounts(fixed, {3: None}) == {1: 101, 2: 102}
    assert resolve_accounts(fixed, {2: 104}) == {1: 101, 2: 104, 3: 103}


RATE = dict(pay_type="hourly", amount=16000, work_start=time(7), work_end=time(13),
            break_min=0, break_paid=True, ot_unit_min=30, ot_unit_amount=5000, vat_applied=False)


def test_check_rate_ok():
    out = check_rate("employee", RATE)
    assert out["amount"] == 16000 and out["ot_unit_min"] == 30 and out["work_start"] == time(7)
    m = check_rate("regular", {**RATE, "pay_type": "monthly", "amount": 3_000_000})
    assert m["work_start"] is None and m["ot_unit_min"] == 0 and m["ot_unit_amount"] == 0


@pytest.mark.parametrize("income,patch,msg", [
    ("regular", {}, "월급제"),
    ("employee", {"pay_type": "monthly"}, "시급제"),
    ("employee", {"amount": 0}, "금액"),
    ("employee", {"work_start": None, "work_end": None}, "지정 출근"),
    ("employee", {"work_end": time(6)}, "늦어야"),
    ("employee", {"break_min": 400}, "휴게"),
    ("business", {"ot_unit_amount": 0}, "초과수당"),
])
def test_check_rate_errors(income, patch, msg):
    with pytest.raises(ValueError, match=msg):
        check_rate(income, {**RATE, **patch})
