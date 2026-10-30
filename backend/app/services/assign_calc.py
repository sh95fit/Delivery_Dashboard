"""S3-P2h 날짜별 계정 → 인력 → 차량 판정 (순수 함수, DB 없음 → 단위 테스트 대상).

- 계정 → 인력: 인센티브 배정과 같은 결과(incentive_calc.assign_owner: 담당 지정 → 근무 기록 → 고정 계정)를 받아 쓴다
- 인력 → 차량: 그날 예외(worker_vehicle_days) → 차량 이용 이력(worker_vehicles, 시작일 이력)
  mode = company(회사 차량) / own(자차) / none(차량 없음)
- 전환 기간: 인력을 못 찾았거나 그 날짜 기준 차량 이력이 없으면 기존 계정 차량 배정(vehicle_assignments) 사용
- 같은 회사 차량을 두 사람이 겹치는 기간에 '이력'으로 쓰는 것은 막는다 (하루만 같이 쓰면 그날 예외로)
- 퇴사일(workers.end_date)이 있으면 그 사람의 이력은 퇴사일에서 끝난 것으로 본다
"""
from __future__ import annotations

from datetime import date, timedelta

from app.services.cost_calc import effective_on

MODES = ("company", "own", "none")
MODE_LABEL = {"company": "회사 차량", "own": "자차", "none": "차량 없음"}
DAY_REASONS = ("breakdown", "swap", "other")
DAY_REASON_LABEL = {"breakdown": "고장·정비", "swap": "교대·대체", "other": "기타"}


def group_by_worker(rows: list[dict]) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(int(r["worker_id"]), []).append(r)
    return out


def vehicle_of(hist_by: dict[int, list[dict]], day_map: dict[tuple[date, int], int | None],
               wid: int, d: date) -> tuple[int | None, str]:
    """인력 wid의 그날 차량 → (vehicle_id, 근거).
    근거 = day(그날 예외) / company / own / none / no_history(그 날짜 기준 이력 없음)"""
    if (d, wid) in day_map:
        return day_map[(d, wid)], "day"
    h = effective_on(hist_by.get(wid, []), d, "start_date")
    if h is None:
        return None, "no_history"
    if h["mode"] == "company":
        return int(h["vehicle_id"]), "company"
    return None, h["mode"]


def resolve(d: date, mid: int, owner: int | None, hist_by: dict[int, list[dict]],
            day_map: dict[tuple[date, int], int | None], legacy: dict[int, dict]) -> dict:
    """계정 mid의 그날 → {worker_id, vehicle_id, basis}.
    owner = 그날 이 계정 담당 인력 (assign_owner 결과, 못 찾으면 None)
    legacy = 그날 기준 계정별 vehicle_assignments 행 (cost_calc.latest_by 결과)
    basis = day / company / own / none / legacy(기존 계정 차량 배정) / unknown(차량 못 찾음)"""
    if owner is not None:
        vid, basis = vehicle_of(hist_by, day_map, owner, d)
        if basis != "no_history":
            return {"worker_id": owner, "vehicle_id": vid, "basis": basis}
    a = legacy.get(mid)
    if a and a.get("vehicle_id"):
        return {"worker_id": owner, "vehicle_id": int(a["vehicle_id"]), "basis": "legacy"}
    return {"worker_id": owner, "vehicle_id": None, "basis": "unknown"}


def users_by_vehicle(resolved: dict[int, dict]) -> dict[int, list[int]]:
    """그날 {계정: resolve 결과} → {차량: [계정, ...]} (한 차량을 두 계정이 쓰면 비용을 똑같이 나눔)"""
    out: dict[int, list[int]] = {}
    for mid, r in sorted(resolved.items()):
        if r.get("vehicle_id"):
            out.setdefault(int(r["vehicle_id"]), []).append(mid)
    return out


def spans(rows: list[dict], ends: dict[int, date | None] | None = None) -> list[dict]:
    """차량 이용 이력 → 인력별 기간 [{worker_id, vehicle_id, start, end}].
    end = 다음 이력 전날 (마지막은 None). ends = {인력: 퇴사일} → 퇴사일에서 끝냄, 퇴사 뒤 시작 이력은 무시"""
    out = []
    for wid, rs in group_by_worker(rows).items():
        rs = sorted(rs, key=lambda r: r["start_date"])
        cap = (ends or {}).get(wid)
        for i, r in enumerate(rs):
            if cap is not None and r["start_date"] > cap:
                continue
            end = rs[i + 1]["start_date"] - timedelta(days=1) if i + 1 < len(rs) else None
            if cap is not None and (end is None or cap < end):
                end = cap
            out.append({"worker_id": wid,
                        "vehicle_id": int(r["vehicle_id"]) if r["mode"] == "company" else None,
                        "start": r["start_date"], "end": end})
    return out


def _overlap(a: dict, b: dict) -> bool:
    return (a["end"] is None or b["start"] <= a["end"]) and (b["end"] is None or a["start"] <= b["end"])


def find_conflict(rows: list[dict], ends: dict[int, date | None] | None = None) -> dict | None:
    """같은 회사 차량을 다른 두 인력이 겹치는 기간에 쓰면 → {vehicle_id, workers, from}. 없으면 None.
    rows = 저장하려는 상태 그대로의 전체 이력 (수정 전 행은 빼고 새 행은 넣어서 넘김)"""
    sp = [s for s in spans(rows, ends) if s["vehicle_id"]]
    for i, a in enumerate(sp):
        for b in sp[i + 1:]:
            if a["vehicle_id"] == b["vehicle_id"] and a["worker_id"] != b["worker_id"] and _overlap(a, b):
                return {"vehicle_id": a["vehicle_id"], "workers": (a["worker_id"], b["worker_id"]),
                        "from": max(a["start"], b["start"])}
    return None


def disposal_problem(rows: list[dict], ends: dict[int, date | None] | None,
                     disposed: dict[int, date]) -> dict | None:
    """[S3-P2h-3b-2] 처분일(disposed = {차량: 처분일}) 뒤에도 그 차량으로 이어지는 이력 → {worker_id, vehicle_id, disposed_on}. 없으면 None.
    rows = 저장하려는 상태 그대로의 전체 이력 (find_conflict와 같은 방식)"""
    for s in spans(rows, ends):
        cap = disposed.get(s["vehicle_id"]) if s["vehicle_id"] else None
        if cap is not None and (s["end"] is None or s["end"] > cap):
            return {"worker_id": s["worker_id"], "vehicle_id": s["vehicle_id"], "disposed_on": cap}
    return None


def check_mode(mode: str, vehicle_id: int | None) -> str | None:
    """[S3-P2h-2a] 차량 이용 이력 저장 전 검사. 문제 없으면 None."""
    if mode not in MODES:
        return "이용 구분을 확인하세요 (회사 차량 / 자차 / 차량 없음)"
    if mode == "company" and not vehicle_id:
        return "회사 차량은 차량을 선택하세요"
    return None


def lock_until(close_months: list[date]) -> date | None:
    """[S3-P2h-2a] 유류비 마감된 달 중 가장 늦은 달의 말일 (없으면 None).
    이 날까지 걸리는 차량 이용 이력·그날 예외는 추가·수정·삭제 불가 (마감된 달의 계정별 금액이 바뀌므로)."""
    if not close_months:
        return None
    m = max(close_months)
    nxt = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    return nxt - timedelta(days=1)
