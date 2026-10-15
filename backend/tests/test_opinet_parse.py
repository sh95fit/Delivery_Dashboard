from datetime import date

from app.services.fuel_calc import opinet_params, parse_opinet

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
