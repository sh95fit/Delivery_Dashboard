from datetime import date as D

from app.services.assign_calc import find_conflict, group_by_worker, resolve, spans, users_by_vehicle, vehicle_of

HIST = [
    {"worker_id": 2, "start_date": D(2026, 10, 1), "mode": "company", "vehicle_id": 1},
    {"worker_id": 3, "start_date": D(2026, 10, 16), "mode": "company", "vehicle_id": 2},
    {"worker_id": 4, "start_date": D(2026, 10, 1), "mode": "company", "vehicle_id": 3},
    {"worker_id": 4, "start_date": D(2026, 10, 16), "mode": "company", "vehicle_id": 4},
    {"worker_id": 5, "start_date": D(2026, 10, 1), "mode": "own", "vehicle_id": None},
]
HB = group_by_worker(HIST)


def test_vehicle_of_period_and_change():
    assert vehicle_of(HB, {}, 4, D(2026, 10, 15)) == (3, "company")
    assert vehicle_of(HB, {}, 4, D(2026, 10, 16)) == (4, "company")
    assert vehicle_of(HB, {}, 5, D(2026, 10, 20)) == (None, "own")
    assert vehicle_of(HB, {}, 3, D(2026, 10, 15)) == (None, "no_history")
    assert vehicle_of(HB, {}, 9, D(2026, 10, 15)) == (None, "no_history")


def test_vehicle_of_day_exception():
    days = {(D(2026, 10, 20), 4): 1, (D(2026, 10, 21), 4): None}
    assert vehicle_of(HB, days, 4, D(2026, 10, 20)) == (1, "day")
    assert vehicle_of(HB, days, 4, D(2026, 10, 21)) == (None, "day")
    assert vehicle_of(HB, days, 4, D(2026, 10, 22)) == (4, "company")


def test_resolve_worker_change_on_account():
    # 계정 1: 10/1~15 인력 2(차량 1), 10/16~ 인력 3(차량 2)
    assert resolve(D(2026, 10, 15), 1, 2, HB, {}, {}) == {"worker_id": 2, "vehicle_id": 1, "basis": "company"}
    assert resolve(D(2026, 10, 16), 1, 3, HB, {}, {}) == {"worker_id": 3, "vehicle_id": 2, "basis": "company"}


def test_resolve_legacy_and_unknown():
    legacy = {7: {"manager_id": 7, "vehicle_id": 5}}
    assert resolve(D(2026, 10, 10), 7, None, HB, {}, legacy) == {"worker_id": None, "vehicle_id": 5, "basis": "legacy"}
    assert resolve(D(2026, 10, 10), 7, 3, HB, {}, legacy)["basis"] == "legacy"     # 인력 3은 10/16 전 이력 없음
    assert resolve(D(2026, 10, 10), 8, None, HB, {}, legacy) == {"worker_id": None, "vehicle_id": None, "basis": "unknown"}
    assert resolve(D(2026, 10, 10), 7, 5, HB, {}, legacy) == {"worker_id": 5, "vehicle_id": None, "basis": "own"}


def test_users_by_vehicle_shared():
    r = {1: {"vehicle_id": 3}, 2: {"vehicle_id": 3}, 3: {"vehicle_id": None}}
    assert users_by_vehicle(r) == {3: [1, 2]}


def test_spans_and_conflict():
    assert spans(HIST[2:4])[0]["end"] == D(2026, 10, 15)
    assert find_conflict(HIST) is None
    bad = HIST + [{"worker_id": 6, "start_date": D(2026, 10, 10), "mode": "company", "vehicle_id": 1}]
    c = find_conflict(bad)
    assert c["vehicle_id"] == 1 and set(c["workers"]) == {2, 6} and c["from"] == D(2026, 10, 10)


def test_conflict_respects_end_date():
    rows = [{"worker_id": 2, "start_date": D(2026, 1, 1), "mode": "company", "vehicle_id": 1},
            {"worker_id": 6, "start_date": D(2026, 10, 16), "mode": "company", "vehicle_id": 1}]
    assert find_conflict(rows) is not None
    assert find_conflict(rows, ends={2: D(2026, 10, 15)}) is None
