from datetime import date as D

from app.services.assign_calc import (BOARD_ERRORS, BOARD_FLAGS, board_flags, check_mode, disposal_problem,
                                      group_by_worker, handover_cuts, hold_spans, lock_until, overlaps,
                                      resolve, spans, users_by_vehicle, vehicle_of)
from app.services.assign_calc import EXCLUDE_REASONS, check_exclude, exclude_on, exclude_overlap

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
    assert resolve(D(2026, 10, 15), 1, 2, HB, {}) == {"worker_id": 2, "vehicle_id": 1, "basis": "company"}
    assert resolve(D(2026, 10, 16), 1, 3, HB, {}) == {"worker_id": 3, "vehicle_id": 2, "basis": "company"}


def test_resolve_unknown():
    # [S3-P2h-3c] 기존 계정 차량 배정 제거 → 인력·이력을 못 찾으면 unknown
    assert resolve(D(2026, 10, 10), 7, None, HB, {}) == {"worker_id": None, "vehicle_id": None, "basis": "unknown"}
    assert resolve(D(2026, 10, 10), 7, 3, HB, {}) == {"worker_id": 3, "vehicle_id": None, "basis": "unknown"}   # 인력 3은 10/16 전 이력 없음
    assert resolve(D(2026, 10, 10), 7, 5, HB, {}) == {"worker_id": 5, "vehicle_id": None, "basis": "own"}


def test_users_by_vehicle_shared():
    r = {1: {"vehicle_id": 3}, 2: {"vehicle_id": 3}, 3: {"vehicle_id": None}}
    assert users_by_vehicle(r) == {3: [1, 2]}


def test_spans_and_overlaps():
    assert spans(HIST[2:4])[0]["end"] == D(2026, 10, 15)
    assert overlaps(HIST, None, "vehicle_id") == []
    bad = HIST + [{"worker_id": 6, "start_date": D(2026, 10, 10), "mode": "company", "vehicle_id": 1}]
    c = overlaps(bad, None, "vehicle_id")
    assert len(c) == 1 and c[0]["value"] == 1 and c[0]["from"] == D(2026, 10, 10)
    assert (c[0]["first"]["worker_id"], c[0]["second"]["worker_id"]) == (2, 6)


def test_overlaps_respects_end_date():
    rows = [{"worker_id": 2, "start_date": D(2026, 1, 1), "mode": "company", "vehicle_id": 1},
            {"worker_id": 6, "start_date": D(2026, 10, 16), "mode": "company", "vehicle_id": 1}]
    assert overlaps(rows, None, "vehicle_id") != []
    assert overlaps(rows, {2: D(2026, 10, 15)}, "vehicle_id") == []


def test_check_mode_and_lock():
    assert check_mode("company", None) == "회사 차량은 차량을 선택하세요"
    assert check_mode("company", 3) is None
    assert check_mode("own", None) is None
    assert check_mode("x", None).startswith("이용 구분")
    assert lock_until([]) is None
    assert lock_until([D(2026, 8, 1), D(2026, 9, 1)]) == D(2026, 9, 30)
    assert lock_until([D(2026, 12, 1)]) == D(2026, 12, 31)


def test_disposal_problem():
    rows = [{"worker_id": 2, "start_date": D(2026, 9, 1), "mode": "company", "vehicle_id": 1},
            {"worker_id": 2, "start_date": D(2026, 10, 28), "mode": "company", "vehicle_id": 4}]
    assert disposal_problem(rows, {}, {1: D(2026, 10, 27)}) is None                       # 10-27까지 쓰고 처분
    assert disposal_problem(rows, {}, {1: D(2026, 10, 20)}) == {"worker_id": 2, "vehicle_id": 1, "disposed_on": D(2026, 10, 20)}
    assert disposal_problem(rows[:1], {}, {1: D(2026, 10, 27)})["worker_id"] == 2         # 다음 이력 없음 → 계속 이어짐
    assert disposal_problem(rows[:1], {2: D(2026, 10, 1)}, {1: D(2026, 10, 27)}) is None  # 퇴사일에서 끝남


# ---------- [S3-P2h-3e] 계정·차량 공통 기간 규칙 ----------
ACC = [{"worker_id": 12, "manager_id": 42, "start_date": D(2026, 8, 1)},
       {"worker_id": 14, "manager_id": 42, "start_date": D(2026, 9, 18)}]
ENDS = {12: D(2026, 9, 18)}


def test_hold_spans_end_date_cap():
    sp = hold_spans(ACC, ENDS, "manager_id")
    a = next(s for s in sp if s["worker_id"] == 12)
    assert (a["value"], a["start"], a["end"]) == (42, D(2026, 8, 1), D(2026, 9, 18))   # 비활성이어도 퇴사일까지
    b = next(s for s in sp if s["worker_id"] == 14)
    assert (b["start"], b["end"]) == (D(2026, 9, 18), None)
    late = ACC + [{"worker_id": 12, "manager_id": 7, "start_date": D(2026, 9, 20)}]
    assert len([s for s in hold_spans(late, ENDS, "manager_id") if s["worker_id"] == 12]) == 1   # 퇴사 뒤 시작 이력 무시


def test_overlaps_handover_day():
    bad = overlaps(ACC, ENDS, "manager_id")
    assert len(bad) == 1 and bad[0]["from"] == D(2026, 9, 18)
    assert bad[0]["first"]["worker_id"] == 12 and bad[0]["second"]["worker_id"] == 14
    assert overlaps(ACC, ENDS, "manager_id", wid=99) == []          # 저장하는 사람이 안 낀 겹침은 무시
    fixed = ACC + [{"worker_id": 12, "manager_id": None, "start_date": D(2026, 9, 18)}]
    assert overlaps(fixed, ENDS, "manager_id") == []                 # 앞사람 '계정 없음' 9/18 → 9/17까지


def test_handover_cuts():
    new = {"worker_id": 14, "manager_id": 42, "start_date": D(2026, 9, 18)}
    assert handover_cuts(ACC[:1], ENDS, "manager_id", new) == [
        {"worker_id": 12, "cut_on": D(2026, 9, 18), "value": 42, "start": D(2026, 8, 1)}]
    same = {"worker_id": 14, "manager_id": 42, "start_date": D(2026, 8, 1)}
    assert handover_cuts(ACC[:1], ENDS, "manager_id", same) == []    # 같은 날 시작은 끊지 않음 → overlaps가 거절
    assert overlaps(ACC[:1] + [same], ENDS, "manager_id") != []
    after = {"worker_id": 14, "manager_id": 42, "start_date": D(2026, 9, 19)}
    assert handover_cuts(ACC[:1], ENDS, "manager_id", after) == []   # 퇴사일 다음 날 시작 → 겹침 없음
    assert handover_cuts(ACC[:1], ENDS, "manager_id", {**new, "manager_id": None}) == []


# ---------- [S3-P2h-3d-2a] 월별 정합성 표 칸 표시 ----------
def test_board_flags():
    d = D(2026, 9, 18)
    ok = {"worker_id": 14, "vehicle_id": 8, "basis": "company"}
    assert board_flags(ok, None, None, False, d) == []
    assert board_flags({"worker_id": None, "vehicle_id": None, "basis": "unknown"}, None, None, True, d) == ["no_worker"]
    gone = {"worker_id": 12, "vehicle_id": None, "basis": "unknown"}
    assert board_flags(gone, D(2026, 9, 17), None, False, d) == ["after_end"]      # 퇴사 다음 날 운행
    assert board_flags(gone, D(2026, 9, 18), None, False, d) == ["no_vehicle"]     # 퇴사일 당일 · 이력 없음
    assert board_flags(ok, None, D(2026, 9, 17), True, d) == ["disposed", "shared"]
    assert board_flags(ok, None, D(2026, 9, 18), False, d) == []                   # 처분일 당일까지는 사용 가능
    assert board_flags({"worker_id": 5, "vehicle_id": None, "basis": "own"}, None, None, False, d) == []
    assert set(BOARD_ERRORS) <= set(BOARD_FLAGS)


# ---------- [S3-P2h-3d-5] 점검 제외 계정 ----------
EXC = [{"id": 1, "manager_id": 1, "reason": "internal", "start_date": D(2026, 9, 1), "end_date": None},
       {"id": 2, "manager_id": 22, "reason": "hold", "start_date": D(2026, 9, 1), "end_date": D(2026, 10, 31)}]


def test_exclude_on():
    assert exclude_on(EXC, 1, D(2026, 11, 12))["id"] == 1        # 종료일 비면 계속
    assert exclude_on(EXC, 1, D(2026, 8, 31)) is None            # 시작일 전
    assert exclude_on(EXC, 22, D(2026, 10, 31))["id"] == 2       # 종료일 당일까지
    assert exclude_on(EXC, 22, D(2026, 11, 1)) is None           # 종료일 다음 날부터 다시 점검
    assert exclude_on(EXC, 38, D(2026, 9, 10)) is None


def test_check_exclude_and_overlap():
    assert check_exclude("internal", D(2026, 9, 1), None) is None
    assert check_exclude("x", D(2026, 9, 1), None).startswith("제외 사유")
    assert check_exclude("hold", D(2026, 9, 2), D(2026, 9, 1)) == "종료일이 시작일보다 빠릅니다"
    assert exclude_overlap(EXC, 22, D(2026, 11, 1), None) is None
    assert exclude_overlap(EXC, 22, D(2026, 10, 31), None)["id"] == 2
    assert exclude_overlap(EXC, 1, D(2025, 1, 1), D(2025, 12, 31)) is None
    assert exclude_overlap(EXC, 1, D(2025, 1, 1), None)["id"] == 1
    assert set(EXCLUDE_REASONS) == {"internal", "hold", "other"}
