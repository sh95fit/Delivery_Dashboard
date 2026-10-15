from datetime import date

import pytest

from app.services.business_days import business_days
from app.services.fuel_log_calc import allocate_month, amounts, log_cost, month_bounds


def test_month_bounds():
    assert month_bounds("2026-09") == (date(2026, 9, 1), date(2026, 9, 30))
    assert month_bounds("2028-02") == (date(2028, 2, 1), date(2028, 2, 29))
    for bad in ("2026", "2026-13", "abc"):
        with pytest.raises(ValueError):
            month_bounds(bad)


def test_amounts():
    assert amounts(144000) == (144000, 130909, 13091)              # 비우면 합계 ÷ 1.1
    assert amounts(144000, supply=131000) == (144000, 131000, 13000)
    assert amounts(144000, vat=13000) == (144000, 131000, 13000)
    assert amounts(144000, 130909, 13091) == (144000, 130909, 13091)
    with pytest.raises(ValueError):
        amounts(144000, 130000, 13000)                             # 합이 안 맞음
    with pytest.raises(ValueError):
        amounts(0)
    with pytest.raises(ValueError):
        amounts(1000, supply=2000)


def test_log_cost():
    r = {"total_amount": 144000, "supply_amount": 130909}
    assert log_cost(r, True) == 130909                             # 공제 차량 = 공급가액
    assert log_cost(r, False) == 144000                            # 불공제 차량 = 합계


def test_allocate_september():
    f, t = month_bounds("2026-09")
    days = list(business_days(f, t))
    assert len(days) == 23                                         # 일요일 4일 + 추석 3일 휴무
    out = allocate_month({1: 3535000, 2: 0}, days, f, t)
    vals = [v[1] for v in out.values()]
    assert sum(vals) == 3535000 and len(vals) == 23
    assert max(vals) - min(vals) <= 1
    assert date(2026, 9, 6) not in out                             # 일요일
    assert date(2026, 9, 25) not in out                            # 추석
    assert all(2 not in v for v in out.values())                   # 0원 차량은 없음


def test_allocate_no_open_days():
    out = allocate_month({7: 3000}, [], date(2026, 9, 1), date(2026, 9, 3))
    assert sum(v[7] for v in out.values()) == 3000 and len(out) == 3
