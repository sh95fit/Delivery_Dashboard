from datetime import date

from app.services.worklog_calc import employed, in_term, work_term

S, E = date(2026, 9, 3), date(2026, 9, 18)


def test_work_term():
    assert work_term({"active": True, "start_date": S, "end_date": None}) == (S, None)
    assert work_term({"active": False, "start_date": None, "end_date": E}) == (None, E)
    assert work_term({"active": False, "start_date": None, "end_date": None}) is None


def test_employed_inclusive():
    t = (S, E)
    assert not employed(date(2026, 9, 2), t)
    assert employed(S, t) and employed(E, t)          # 입사일·퇴사일 당일 포함
    assert not employed(date(2026, 9, 19), t)
    assert employed(date(2030, 1, 1), (None, None))
    assert not employed(S, None)


def test_in_term():
    t = (S, E)
    assert in_term(date(2026, 9, 1), date(2026, 9, 30), t)
    assert not in_term(date(2026, 10, 1), date(2026, 10, 31), t)
    assert not in_term(date(2026, 8, 1), date(2026, 8, 31), t)
    assert in_term(date(2026, 8, 1), date(2026, 8, 31), (None, E))
    assert not in_term(date(2026, 9, 1), date(2026, 9, 30), None)
