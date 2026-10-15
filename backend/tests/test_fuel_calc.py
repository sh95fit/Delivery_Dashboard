from datetime import date

from app.services.fuel_calc import direct_fuel_cost, parse_opinet, price_on

D = date(2026, 10, 14)


def test_parse_opinet_all():
    payload = {"RESULT": {"OIL": [
        {"TRADE_DT": "20261013", "PRODCD": "B027", "PRICE": "1667.33"},
        {"TRADE_DT": "20261013", "PRODCD": "D047", "PRICE": "1532.22"},
        {"TRADE_DT": "20261013", "PRODCD": "K015", "PRICE": "1052.64"},
        {"TRADE_DT": "20261013", "PRODCD": "B034", "PRICE": "1919.44"},
        {"TRADE_DT": "20261013", "PRODCD": "C004", "PRICE": "1295.23"},
    ]}}
    out = parse_opinet(payload, D)
    assert {o["fuel_type"]: o["price"] for o in out} == {"gasoline": 1667.33, "diesel": 1532.22, "lpg": 1052.64}
    assert all(o["price_date"] == date(2026, 10, 13) for o in out)


def test_parse_opinet_sido_without_date_and_bad_rows():
    sido = {"RESULT": {"OIL": [{"SIDOCD": "01", "PRODCD": "D047", "PRICE": "1620.41"}]}}
    assert parse_opinet(sido, D) == [{"price_date": D, "fuel_type": "diesel", "price": 1620.41}]
    assert parse_opinet({}, D) == []
    assert parse_opinet({"RESULT": {"OIL": [{"TRADE_DT": "x", "PRODCD": "B027", "PRICE": "1"}]}}, D) == []


def test_price_on_latest_and_manual_wins():
    rows = [
        {"fuel_type": "diesel", "price_date": date(2026, 10, 1), "source": "opinet", "price": 1500},
        {"fuel_type": "diesel", "price_date": date(2026, 10, 5), "source": "opinet", "price": 1520},
        {"fuel_type": "diesel", "price_date": date(2026, 10, 5), "source": "manual", "price": 1490},
        {"fuel_type": "ev", "price_date": date(2026, 9, 1), "source": "manual", "price": 324.4},
    ]
    assert price_on(rows, "diesel", date(2026, 10, 3))["price"] == 1500
    assert price_on(rows, "diesel", date(2026, 10, 9))["price"] == 1490
    assert price_on(rows, "ev", date(2026, 10, 9))["price"] == 324.4
    assert price_on(rows, "lpg", date(2026, 10, 9)) is None


def test_direct_fuel_cost():
    assert direct_fuel_cost(80_000, 10, 1532.22) == 12_258
    assert direct_fuel_cost(80_000, None, 1532.22) is None
