from datetime import date, timedelta

from app.services.business_days import business_days, rule_closed, split_over


def test_october_2026_rule():
    days = business_days(date(2026, 10, 1), date(2026, 10, 31))
    assert len(days) == 25                      # 31일 - 일요일 4일 - 개천절 - 한글날
    assert date(2026, 10, 3) not in days        # 개천절(토)
    assert date(2026, 10, 4) not in days        # 일요일
    assert date(2026, 10, 5) in days            # 개천절 대체공휴일 → 정상 영업
    assert date(2026, 10, 9) not in days        # 한글날(금)
    assert date(2026, 10, 10) in days           # 토요일 영업
    assert rule_closed(date(2026, 10, 4)) == "일요일"


def test_overrides_win():
    ov = {date(2026, 10, 9): {"is_open": True, "memo": "한글날 정상 영업"},
          date(2026, 10, 10): {"is_open": False, "memo": None}}
    days = business_days(date(2026, 10, 1), date(2026, 10, 31), ov)
    assert len(days) == 25
    assert date(2026, 10, 9) in days and date(2026, 10, 10) not in days


def test_split_over_sums_exactly():
    days = [date(2026, 9, 1) + timedelta(days=i) for i in range(23)]
    s = split_over(442_000, days)
    assert sum(s.values()) == 442_000
    assert s[days[0]] == 19_218 and s[days[-1]] == 19_217
    assert split_over(1000, []) == {}
