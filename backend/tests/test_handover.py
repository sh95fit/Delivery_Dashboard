"""S3-P2h-3e 계정·차량 공통 기간 규칙 (hold_spans · overlaps · handover_cuts)."""
from datetime import date as D

from app.services.assign_calc import handover_cuts, hold_spans, overlaps


def V(w, s, v):     # 차량 이용 이력 행 (v = 회사 차량 id, None = 차량 없음·자차)
    return {"worker_id": w, "start_date": s, "vehicle_id": v}


def A(w, s, m):     # 고정 계정 이력 행 (m = 계정 id, None = 계정 없음)
    return {"worker_id": w, "start_date": s, "manager_id": m}


def test_cut_previous_holder_kimtaehoon_case():
    rows = [V(12, D(2026, 8, 1), 8)]
    ends = {12: D(2026, 9, 18)}
    cuts = handover_cuts(rows, ends, "vehicle_id", V(14, D(2026, 9, 18), 8))
    assert cuts == [{"worker_id": 12, "cut_on": D(2026, 9, 18), "value": 8, "start": D(2026, 8, 1)}]
    state = rows + [V(12, D(2026, 9, 18), None), V(14, D(2026, 9, 18), 8)]
    assert overlaps(state, ends, "vehicle_id") == []


def test_same_day_start_not_cut_and_rejected():
    rows = [V(12, D(2026, 9, 18), 8)]
    assert handover_cuts(rows, {}, "vehicle_id", V(14, D(2026, 9, 18), 8)) == []
    bad = overlaps(rows + [V(14, D(2026, 9, 18), 8)], {}, "vehicle_id")
    assert len(bad) == 1 and bad[0]["first"]["start"] == bad[0]["second"]["start"]


def test_retired_before_handover_no_cut():
    rows = [V(12, D(2026, 8, 1), 8)]
    assert handover_cuts(rows, {12: D(2026, 9, 17)}, "vehicle_id", V(14, D(2026, 9, 18), 8)) == []


def test_account_retired_on_handover_day_overlaps():
    # 퇴사일(9/18)까지 앞사람 기간 → 9/18 시작과 하루 겹침 (예전 계정 검사는 비활성 인력을 무시해 통과시켰음)
    rows = [A(12, D(2026, 8, 1), 42), A(14, D(2026, 9, 18), 42)]
    bad = overlaps(rows, {12: D(2026, 9, 18)}, "manager_id")
    assert len(bad) == 1
    assert bad[0]["from"] == D(2026, 9, 18) and bad[0]["first"]["worker_id"] == 12
    fixed = rows + [A(12, D(2026, 9, 18), None)]
    assert overlaps(fixed, {12: D(2026, 9, 18)}, "manager_id") == []


def test_overlap_filter_by_worker():
    rows = [A(1, D(2026, 1, 1), 7), A(2, D(2026, 2, 1), 7), A(3, D(2026, 1, 1), 9)]
    assert len(overlaps(rows, {}, "manager_id")) == 1
    assert overlaps(rows, {}, "manager_id", 3) == []
    assert len(overlaps(rows, {}, "manager_id", 2)) == 1


def test_cut_keeps_later_rows():
    rows = [V(1, D(2026, 8, 1), 8), V(1, D(2026, 10, 1), 5)]
    cuts = handover_cuts(rows, {}, "vehicle_id", V(2, D(2026, 9, 1), 8))
    assert [c["cut_on"] for c in cuts] == [D(2026, 9, 1)]
    sp = hold_spans(rows + [V(1, D(2026, 9, 1), None)], {}, "vehicle_id")
    assert [(s["start"], s["end"], s["value"]) for s in sp] == [
        (D(2026, 8, 1), D(2026, 8, 31), 8), (D(2026, 9, 1), D(2026, 9, 30), None), (D(2026, 10, 1), None, 5)]


def test_none_value_never_cuts():
    assert handover_cuts([V(1, D(2026, 8, 1), 8)], {}, "vehicle_id", V(2, D(2026, 9, 1), None)) == []


def test_new_person_earlier_than_other_not_cut():
    # 새 행이 다른 사람보다 먼저 시작해 뒤 기간과 겹치는 경우 → 끊지 않음, overlaps가 거절
    rows = [V(1, D(2026, 9, 1), 8)]
    assert handover_cuts(rows, {}, "vehicle_id", V(2, D(2026, 8, 1), 8)) == []
    assert len(overlaps(rows + [V(2, D(2026, 8, 1), 8)], {}, "vehicle_id")) == 1
