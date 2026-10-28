from datetime import date

import pytest

from app.services.ev_rate_calc import guess_meta, parse_matrix, rate_on, read_settings

HEAD = ["발급/이용", "기후에너지환경부", "한국전력공사", "GS차지비", "채비", "에버온"]
ROWS = [
    ["로밍 요금 매트릭스(초급속(200kW 이상))"],
    HEAD,
    ["한국전력공사", 393.1, 385, "-", 450, 420],
    ["기후에너지환경부", 393.1, 393.1, "-", "470.5", None],
]


def test_parse_matrix():
    m = parse_matrix(ROWS)
    assert m["issuer"] == "기후에너지환경부"
    assert m["header_row"] == 2
    assert m["base_operator"] == "기후에너지환경부" and m["base_price"] == 393.1
    assert m["rates"] == [{"operator": "기후에너지환경부", "price": 393.1},
                          {"operator": "한국전력공사", "price": 393.1},
                          {"operator": "채비", "price": 470.5}]
    assert m["skipped"] == 2


def test_parse_matrix_empty_corner():
    rows = [[None] + HEAD[1:], ["기후에너지환경부", 347.2, 300, 310, 320, 330]]
    m = parse_matrix(rows)
    assert m["base_price"] == 347.2 and len(m["rates"]) == 5


def test_parse_matrix_errors():
    with pytest.raises(ValueError):
        parse_matrix([["아무", "내용"]])
    with pytest.raises(ValueError):
        parse_matrix([HEAD, ["한국전력공사", 393.1, 385, 1, 2, 3]])
    with pytest.raises(ValueError):
        parse_matrix([HEAD, ["기후에너지환경부", "-", 385, 1, 2, 3]])


def test_guess_meta():
    assert guess_meta("로밍 요금 매트릭스(초급속(200kW 이상))_2026-10-22.xlsx") == {"speed": "ultra", "effective_from": date(2026, 10, 22)}
    assert guess_meta("로밍 요금 매트릭스(급속)_20261101.xlsx") == {"speed": None, "effective_from": date(2026, 11, 1)}
    assert guess_meta("로밍 요금 매트릭스(급속(50~99kW))_2026-10-27.xlsx")["speed"] == "fast50"
    assert guess_meta("로밍 요금 매트릭스(급속(100~199kW))_2026-10-27.xlsx")["speed"] == "fast100"
    assert guess_meta("로밍 요금 매트릭스(중속(30~49kW))_2026-10-27.xlsx")["speed"] == "mid"
    assert guess_meta("로밍 요금 매트릭스(완속(30kW 미만))_2026-10-27.xlsx")["speed"] == "slow"
    assert guess_meta("matrix.xlsx") == {"speed": None, "effective_from": None}
    assert guess_meta(None) == {"speed": None, "effective_from": None}


def test_rate_on():
    sets = [{"speed": "ultra", "effective_from": date(2026, 10, 22), "base_price": 393.1},
            {"speed": "fast50", "effective_from": date(2026, 11, 1), "base_price": 325.6},
            {"speed": "fast100", "effective_from": date(2026, 11, 1), "base_price": 348.4}]
    assert rate_on(sets, "fast50", date(2026, 11, 5)) == {"price": 325.6, "speed": "fast50", "effective_from": date(2026, 11, 1), "early": False}
    assert rate_on(sets, "fast50", date(2026, 10, 25))["speed"] == "ultra"        # 그날 이전 급속 없음 → 있는 속도
    assert rate_on(sets, "mid", date(2026, 11, 5))["speed"] == "fast50"           # 중속 없음 → 가까운 속도
    r = rate_on(sets, "fast50", date(2026, 9, 1))                                  # 이전 단가 없음 → 가장 이른 단가
    assert r["speed"] == "fast50" and r["early"] is True
    assert rate_on([], "fast50", date(2026, 9, 1)) is None


def test_read_settings():
    assert read_settings([]) == {"ev_speed": "fast50", "ev_km_per_kwh": 3.1}
    assert read_settings([{"key": "ev_speed", "value": "ultra"}, {"key": "ev_km_per_kwh", "value": "4.2"}]) == \
        {"ev_speed": "ultra", "ev_km_per_kwh": 4.2}
    assert read_settings([{"key": "ev_speed", "value": "fast"}])["ev_speed"] == "fast50"     # 예전 값 → 급속 50~99kW
    assert read_settings([{"key": "ev_speed", "value": "x"}, {"key": "ev_km_per_kwh", "value": "abc"}]) == \
        {"ev_speed": "fast50", "ev_km_per_kwh": 2.5}


def test_parse_matrix_issuer_suffix():
    rows = [["발급/이용", "기후에너지환경부(환경부)", "한국전력공사", "채비"],
            ["기후에너지환경부(환경부)", 393.1, "393.1", "470.5"]]
    m = parse_matrix(rows)
    assert m["base_price"] == 393.1
    assert len(m["rates"]) == 3


def test_parse_matrix_header_error_shows_top():
    with pytest.raises(ValueError, match="읽힌 위쪽 내용: 아무"):
        parse_matrix([["아무", "내용"]])