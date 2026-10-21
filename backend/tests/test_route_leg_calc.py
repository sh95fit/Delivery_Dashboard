from datetime import datetime, timedelta, timezone

from datetime import date

from app.services.route_leg_calc import (DEFAULT_DWELL_MS, alloc, chunks, control_summary, coord_key, d5_code, delay_min,
                                         dwell_ms, pending_groups, preview_input, split_legs, target_at)

KST = timezone(timedelta(hours=9))
T = lambda m: datetime(2026, 10, 20, 7, 0, tzinfo=KST) + timedelta(minutes=m)  # noqa: E731


def S(i, lat, lng, m):
    return {"id": str(i), "lat": lat, "lng": lng, "at": T(m)}


def test_pending_groups():
    stops = [S(3, 37.3, 127.3, 30), S(1, 37.1, 127.1, 10), S(2, 37.1, 127.1, 20), S(9, 37.0, 127.0, 5), S(4, 37.4, 127.4, 40)]
    merge, groups = pending_groups(stops, {"4"}, coord_key(37.0, 127.0))
    assert merge == ["9"]                                   # 마지막 지점과 같은 좌표 → 호출 없이 붙임
    assert [g["ids"] for g in groups] == [["1", "2"], ["3"]]  # 완료 순, 연속 같은 좌표는 하나, 이미 연결된 4 제외


def test_chunks():
    assert [len(c) for c in chunks(list(range(13)))] == [6, 6, 1]


ROUTE = {"summary": {"distance": 791, "duration": 120000, "fuelPrice": 100, "tollFare": 0},
         "path": [[127.0, 37.0], [127.001, 37.0], [127.002, 37.0], [127.003, 37.0]],
         "guide": [{"pointIndex": 1, "type": 2, "distance": 300, "duration": 40000},
                   {"pointIndex": 2, "type": 87, "distance": 246, "duration": 30000},
                   {"pointIndex": 3, "type": 88, "distance": 245, "duration": 50000}]}


def test_split_legs():
    legs = split_legs(ROUTE, 2)
    assert [x["distance_m"] for x in legs] == [546, 245]
    assert [x["duration_ms"] for x in legs] == [70000, 50000]
    assert legs[0]["path"] == ROUTE["path"][0:3] and legs[1]["path"] == ROUTE["path"][2:4]
    assert split_legs(ROUTE, 3) is None
    assert split_legs(None, 1) is None
    one = split_legs({"summary": {"distance": 50, "duration": 9000}, "path": [[1, 2]], "guide": []}, 1)
    assert one[0]["distance_m"] == 50


def test_alloc():
    assert alloc(100, [546, 245]) == [69, 31]
    assert sum(alloc(1001, [1, 1, 1])) == 1001
    assert alloc(0, [5, 5]) == [0, 0]
    assert alloc(7, []) == []


def test_d5_code():
    assert d5_code(200, {"code": 0}) == 0
    assert d5_code(400, {"error": {"errorCode": 400, "code": 1, "message": "출발지와 도착지가 동일합니다."}}) == 1
    assert d5_code(400, {}) is None
    assert d5_code(401, {"error": {"errorCode": "210", "message": "Permission Denied"}}) is None
    assert d5_code(500, {"code": 0}) is None


def P(i, mid, lat, at, seq, coord=True):
    return {"delivery_id": i, "has_coord": coord, "manager_id": mid, "latitude": lat if coord else None,
            "longitude": lat + 90 if coord else None, "delivered_at": at, "seq": seq}


def test_preview_input():
    o = {"lat": 37.0, "lng": 127.0}
    stops = [P("a", 7, 37.1, "2026-10-19T23:00:00", 1), P("b", 7, 37.2, "2026-10-19T23:30:00", 2),
             P("d", 7, 37.4, None, 4), P("c", 7, 37.3, None, 3), P("x", 8, 37.9, None, 1), P("n", 7, 0, None, 5, coord=False)]
    start, left, sig = preview_input(stops, 7, o)
    assert (start["lat"], start["lng"]) == (37.2, 127.2)      # 출발 = 마지막 완료 지점
    assert [p["id"] for p in left] == ["c", "d"]               # 미완료만, 배송 순서대로, 좌표 없는 곳 제외
    s8, left8, sig8 = preview_input(stops, 8, o)
    assert s8 == o and [p["id"] for p in left8] == ["x"] and sig8 != sig   # 완료 없으면 출발지에서
    assert preview_input(stops, 7, o)[2] == sig                # 같은 상태면 같은 sig (다시 호출 안 함)


def test_target_at():
    assert target_at(date(2026, 10, 21), "11:30") == datetime(2026, 10, 21, 11, 30, tzinfo=KST)
    assert target_at(date(2026, 10, 21), None) is None
    assert target_at(date(2026, 10, 21), "x") is None


def test_dwell_ms():
    assert dwell_ms([(T(0), 0), (T(10), 0)]) == DEFAULT_DWELL_MS                       # 3곳 미만 → 기본 3분
    assert dwell_ms([(T(0), 600000), (T(10), 360000), (T(20), 360000)]) == 240000      # 20분 − 주행 12분 = 정차 4분씩
    assert dwell_ms([(T(0), 0), (T(0), 0), (T(1), 0)]) == 60000                        # 하한 1분


def test_delay_min():
    assert delay_min(T(68), T(68) - timedelta(seconds=30)) == 0   # 30초 늦음 → 지연 아님 (1분 미만)
    assert delay_min(T(72), T(68)) == 4
    assert delay_min(T(60), T(68)) == -8
    assert delay_min(T(60), None) is None


def test_control_summary():
    now = T(60)
    groups = [{"ids": ["a"], "distance_m": 1000, "duration_ms": 300000},     # 계산 뒤 완료 → 제외
              {"ids": ["b"], "distance_m": 2000, "duration_ms": 600000},
              {"ids": ["c"], "distance_m": 3000, "duration_ms": 600000},
              {"ids": ["x"], "skipped": True}]
    target = {"b": T(68) - timedelta(seconds=30), "c": T(70), "x": None, "n": None}
    c = control_summary(groups, ["b", "c", "x", "n"], T(55), 180000, now, target, 15, True)
    # b: 55+3+10 = 68분 (희망 67분 30초 → 30초 늦음 = 정시), c: 68+3+10 = 81분 > 희망 70분 → 11분 지연
    assert c["state"] == "late" and c["remaining"] == 4
    assert [(x["id"], x["delay_min"]) for x in c["late"]] == [("c", 11)]
    assert [x["delay_min"] for x in c["stops"]] == [0, 11, None, None]
    assert c["no_time_ids"] == ["x", "n"] and c["uncalc_n"] == 1 and c["skipped_n"] == 1
    assert (c["remaining_m"], c["remaining_drive_ms"]) == (5000, 1200000)
    assert c["finish_at"] == T(81).isoformat() and c["idle_min"] == 5 and c["behind_min"] == -8
    one = [{"ids": ["c"], "distance_m": 3000, "duration_ms": 600000}]
    # 30분 완료 → c 예정 43분, 지금 60분 = 17분 지남
    w = control_summary(one, ["c"], T(30), 180000, now, {"c": T(80)}, 15, True)
    assert w["state"] == "wait" and w["behind_min"] == 17                  # 지금 출발해도 70분 도착 ≤ 희망 80분 → 대기
    s = control_summary(one, ["c"], T(30), 180000, now, {"c": T(65)}, 15, True)
    assert s["state"] == "stalled" and s["finish_at"] == now.isoformat()   # 희망 65분 못 맞춤 → 정체
    assert control_summary(one, ["c"], T(30), 180000, now, {"c": None}, 15, True)["state"] == "stalled"
    assert control_summary(one, ["c"], T(50), 180000, now, {"c": T(65)}, 15, True)["state"] == "ok"   # 예정 63분, 15분 안 지남
    assert control_summary([], [], T(30), 180000, now, {}, 15, True)["state"] == "done"
    assert control_summary(groups, ["b"], None, 180000, now, target, 15, True)["state"] == "before"
    assert control_summary(groups, ["b"], T(30), 180000, now, target, 15, False)["state"] == "incomplete"
