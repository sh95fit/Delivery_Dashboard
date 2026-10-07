from datetime import date, time

import pytest

from app.services.worklog_calc import check_log, day_result, month_summary, sheet_break

T = date(2026, 10, 7)
D = date(2026, 10, 1)
R = dict(pay_type="hourly", amount=16000, vat_applied=False, work_start=time(7), work_end=time(12, 30),
         break_min=0, break_paid=True, ot_unit_min=30, ot_unit_amount=5000, effective_from=D)


def L(day, out, cin=time(7), brk=None):
    return {"work_date": date(2026, 10, day), "clock_in": cin, "clock_out": out, "break_min": brk}


def test_check_log_recognized_in():
    v = check_log(time(6, 41), time(13, 13), None, R, day=D, today=T)
    assert (v["clock_in"], v["punch_in"], v["warns"]) == (time(7), time(6, 41), [])
    v = check_log(None, time(12, 30), None, R, day=D, today=T)
    assert (v["clock_in"], v["punch_in"]) == (time(7), None)
    assert check_log(time(7, 10), time(12, 30), None, R, day=D, today=T)["clock_in"] == time(7, 10)


@pytest.mark.parametrize("patch,msg", [
    ({"day": date(2026, 10, 8)}, "미래"),
    ({"rate": None}, "시급 계약"),
    ({"rate": {**R, "pay_type": "monthly"}}, "시급 계약"),
    ({"out": None}, "퇴근"),
    ({"out": time(6, 50)}, "늦어야"),
    ({"brk": 400}, "휴게"),
])
def test_check_log_errors(patch, msg):
    a = {"day": D, "rate": R, "out": time(12, 30), "brk": None, **patch}
    with pytest.raises(ValueError, match=msg):
        check_log(time(7), a["out"], a["brk"], a["rate"], day=a["day"], today=T)


def test_check_log_warns():
    v = check_log(time(6), time(19), None, {**R, "work_start": time(6)}, day=D, today=T)
    assert any("12시간" in w for w in v["warns"]) and any("지정 퇴근" in w for w in v["warns"])
    assert any("1시간" in w for w in check_log(time(8, 30), time(12, 30), None, R, day=D, today=T)["warns"])


def test_sheet_break():
    assert sheet_break(None, R) == 0
    assert sheet_break(None, {**R, "break_min": 30, "break_paid": False}) == 30
    assert sheet_break(None, {**R, "break_min": 30, "break_paid": True}) == 0
    assert sheet_break(20, {**R, "break_min": 30, "break_paid": True}) == 20


def test_day_result():
    d = day_result(L(1, time(13, 13)), R)
    assert (d["paid"], d["ot"], d["ot_pay"], d["rate"]) == (373, 43, 5000, 16000)
    d = day_result(L(1, time(13, 30)), {**R, "work_end": time(13, 30), "break_min": 30, "break_paid": False})
    assert (d["paid"], d["ot"], d["break"]) == (360, 0, 30)


def test_month_summary_sheet_vs_expected():
    s = month_summary([L(1, time(13, 13)), L(2, time(12, 30))], [R])
    assert (s["days"], s["paid_min"], s["ot_min"], s["base"], s["ot_allow"]) == (2, 703, 43, 187467, 5000)
    assert s["pay"]["sheet"]["total"] == 187467          # 근무표: 초과수당 없음
    assert s["pay"]["expected"]["total"] == 192467       # 화면 예상


def test_month_summary_rate_change_and_no_contract():
    r2 = {**R, "amount": 17000, "effective_from": date(2026, 10, 2)}
    assert month_summary([L(1, time(12)), L(2, time(12))], [R, r2])["base"] == 165000
    s = month_summary([{**L(1, time(12)), "work_date": date(2026, 9, 30)}], [R])
    assert (s["days"], s["nocontract"]) == (0, 1)


def test_month_summary_no_rule_vat():
    r = {**R, "amount": 27500, "ot_unit_min": 0, "ot_unit_amount": 0, "vat_applied": True}
    s = month_summary([L(1, time(12))], [r])
    assert s["pay"]["expected"] is None
    assert s["pay"]["sheet"] == {"supply": 137500, "vat": 13750, "total": 151250}
