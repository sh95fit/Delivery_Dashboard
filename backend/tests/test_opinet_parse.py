from datetime import date, timedelta

from app.services.fuel_calc import (add_basis, finish_basis, missing_chunks, opinet_params, parse_opinet,
                                    ref_price)

D = date(2026, 10, 15)


def test_params_use_code():
    assert opinet_params("KEY") == {"out": "json", "code": "KEY"}
    assert opinet_params("KEY", "01") == {"out": "json", "code": "KEY", "sido": "01"}
    assert "certkey" not in opinet_params("KEY")


def test_parse_all_price():
    payload = {"RESULT": {"OIL": [
        {"TRADE_DT": "20261015", "PRODCD": "B034", "PRODNM": "고급휘발유", "PRICE": "2387.49", "DIFF": "+2.95"},
        {"TRADE_DT": "20261015", "PRODCD": "B027", "PRODNM": "휘발유", "PRICE": "1856.44", "DIFF": "-0.06"},
        {"TRADE_DT": "20261015", "PRODCD": "D047", "PRODNM": "자동차용경유", "PRICE": "1,750.10", "DIFF": "0"},
    ]}}
    assert parse_opinet(payload, date(2026, 1, 1)) == [
        {"price_date": D, "fuel_type": "gasoline", "price": 1856.44},     # 고급휘발유는 제외
        {"price_date": D, "fuel_type": "diesel", "price": 1750.1},
    ]


def test_parse_sido_and_empty():
    one = {"RESULT": {"OIL": {"SIDOCD": "01", "SIDONM": "서울", "PRODCD": "K015", "PRICE": "1100.5"}}}
    assert parse_opinet(one, D) == [{"price_date": D, "fuel_type": "lpg", "price": 1100.5}]   # 날짜 없으면 오늘
    assert parse_opinet({"RESULT": {"OIL": []}}, D) == []                                      # certkey로 보냈을 때 응답


def test_parse_daily_date_key():
    payload = {"RESULT": {"OIL": [
        {"DATE": "20260917", "AREA_CD": "01", "PRODCD": "D047", "PRICE": 1886.77},
        {"DATE": "20260917", "AREA_CD": "01", "PRODCD": "C004", "PRICE": 1500},
    ]}}
    assert parse_opinet(payload, D) == [{"price_date": date(2026, 9, 17), "fuel_type": "diesel", "price": 1886.77}]


def test_missing_chunks():
    f, t = date(2026, 9, 1), date(2026, 9, 30)
    assert missing_chunks(set(), f, t) == [date(2026, 9, 30), date(2026, 9, 23), date(2026, 9, 16),
                                           date(2026, 9, 9), date(2026, 9, 2)]
    have = {f + timedelta(days=i) for i in range(30)} - {date(2026, 9, 10)}
    assert missing_chunks(have, f, t) == [date(2026, 9, 10)]


def test_ref_price():
    rows = [{"price_date": date(2026, 9, 22), "fuel_type": "diesel", "price": 1800, "source": "opinet"}]
    assert ref_price(rows, "diesel", date(2026, 9, 23), 1980) == {
        "ref_price": 1800.0, "ref_date": "2026-09-22", "ref_source": "opinet", "ref_diff": 10.0}
    assert ref_price(rows, "gasoline", date(2026, 9, 23), 1980)["ref_price"] is None
    assert str(ref_price(rows, "diesel", date(2026, 9, 23), 1799.5)["ref_diff"]) == "0.0"   # -0.0 표시 방지


def test_basis():
    acc = {}
    add_basis(acc, 50, 90000, 1800)
    add_basis(acc, 50, 95000, 1850)
    add_basis(acc, None, 30000, 1800)          # 수량 없는 기록은 단가 계산에서 제외
    assert finish_basis(acc) == {"avg_unit": 1850.0, "avg_ref": 1825.0, "ref_diff": 1.4}
