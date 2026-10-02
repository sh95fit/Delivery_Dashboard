from datetime import date, timedelta

from app.services import cost_calc as cc

Y0, Y1 = date(2026, 1, 1), date(2026, 12, 31)


def test_allocate_full_period_exact():
    assert cc.allocate_period(1_000_000, Y0, Y1, Y0, Y1) == 1_000_000


def test_allocate_months_sum_to_amount():
    total = 0
    for m in range(1, 13):
        frm = date(2026, m, 1)
        to = (date(2026, m + 1, 1) - timedelta(days=1)) if m < 12 else Y1
        total += cc.allocate_period(1_000_000, Y0, Y1, frm, to)
    assert total == 1_000_000


def test_allocate_remainder_front_loaded():
    # 1,000,000 / 365 = 2739 … 265 → 앞 265일은 2740원
    assert cc.allocate_period(1_000_000, Y0, Y1, date(2026, 1, 1), date(2026, 1, 31)) == 2740 * 31
    assert cc.allocate_period(1_000_000, Y0, Y1, date(2026, 10, 1), date(2026, 10, 31)) == 2739 * 31


def test_allocate_partial_and_no_overlap():
    s, e = date(2026, 3, 15), date(2027, 3, 14)          # 365일
    assert cc.allocate_period(365_000, s, e, date(2026, 3, 1), date(2026, 3, 31)) == 17_000
    assert cc.allocate_period(365_000, s, e, date(2025, 1, 1), date(2025, 12, 31)) == 0
    assert cc.allocate_period(0, s, e, s, e) == 0


def test_effective_on_and_latest_by():
    rows = [
        {"m": 1, "d": date(2026, 1, 1), "v": "a"},
        {"m": 1, "d": date(2026, 9, 1), "v": "b"},
        {"m": 1, "d": date(2026, 12, 1), "v": "future"},
        {"m": 2, "d": date(2026, 11, 1), "v": "c"},
    ]
    assert cc.effective_on(rows[:3], date(2026, 10, 2), "d")["v"] == "b"
    assert cc.effective_on(rows[:3], date(2025, 12, 31), "d") is None
    got = cc.latest_by(rows, "m", "d", date(2026, 10, 2))
    assert got[1]["v"] == "b" and 2 not in got
