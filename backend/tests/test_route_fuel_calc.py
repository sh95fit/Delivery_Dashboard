from datetime import date, datetime, timezone

from app.services.route_fuel_calc import direct_cost, ncp_default, parse_key, pick_routes, price_index, price_on


def test_parse_key():
    assert parse_key("2026-10-15:12:RESULT:db-1,2:abc") == (date(2026, 10, 15), 12, "RESULT")
    assert parse_key("bad") is None
    assert parse_key("2026-10-15:x:RESULT:a") is None


def _r(key, dist, ncp, hour):
    return {"route_key": key, "distance_m": dist, "fuel_price_naver": ncp,
            "created_at": datetime(2026, 10, 15, hour, tzinfo=timezone.utc)}


def test_pick_routes():
    rows = [
        _r("2026-10-15:12:LIVE:o:a", 30000, 4000, 5),
        _r("2026-10-15:12:RESULT:o:b", 42000, 5600, 3),
        _r("2026-10-15:12:RESULT:o:c", 45000, 6000, 4),
        _r("2026-10-15:7:PREVIEW:o:d", 0, 0, 1),
    ]
    got = pick_routes(rows)
    assert list(got) == [(date(2026, 10, 15), 12)]
    assert got[(date(2026, 10, 15), 12)]["distance_m"] == 45000


def test_price_on():
    idx = price_index([
        {"id": 1, "price_date": date(2026, 10, 14), "fuel_type": "diesel", "price": 1880, "source": "opinet"},
        {"id": 2, "price_date": date(2026, 10, 15), "fuel_type": "diesel", "price": 1885.49, "source": "opinet"},
        {"id": 3, "price_date": date(2026, 10, 15), "fuel_type": "diesel", "price": 1900, "source": "manual"},
    ])
    assert price_on(idx, "diesel", date(2026, 10, 14)) == 1880
    assert price_on(idx, "diesel", date(2026, 10, 15)) == 1900
    assert price_on(idx, "diesel", date(2026, 10, 13)) is None
    assert price_on(idx, "ev", date(2026, 10, 15)) is None


def test_direct_cost():
    assert direct_cost(45000, 9.0, 1900) == 9500
    assert direct_cost(45000, None, 1900) is None
    assert direct_cost(45000, 9.0, None) is None
    assert direct_cost(0, 9.0, 1900) is None


def test_pick_routes_actual_only():
    rows = [
        _r("2026-09-23:15:LIVE:o:a", 36736, 4875, 5),
        _r("2026-09-23:15:REMAINING:o:b", 10097, 1300, 5),
        _r("2026-09-23:15:COMPLETED_FIXED:o:c", 26639, 3400, 4),
        _r("2026-09-23:42:PREVIEW:o:d", 20000, 2000, 1),
    ]
    got = pick_routes(rows)
    assert list(got) == [(date(2026, 9, 23), 15)]
    assert got[(date(2026, 9, 23), 15)]["distance_m"] == 26639


def test_ncp_default():
    assert ncp_default(1400, None) == 1400        # 연비 없음 → NAVER 기본 연비 값 그대로
    assert ncp_default(1400, 14.0) == 1400
    assert ncp_default(1400, 7) == 2800           # 연비 7km/L → 기본(14)의 2배
    assert ncp_default(1400, "9.5") == 2063
    assert ncp_default(0, 9) == 0
    assert ncp_default(1400, "bad") == 1400
