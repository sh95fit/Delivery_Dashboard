"""S3-P2h 날짜별 계정 → 인력 → 차량 판정 (순수 함수, DB 없음 → 단위 테스트 대상).

- 계정 → 인력: 인센티브 배정과 같은 결과(incentive_calc.assign_owner: 담당 지정 → 근무 기록 → 고정 계정)를 받아 쓴다
- 인력 → 차량: 그날 예외(worker_vehicle_days) → 차량 이용 이력(worker_vehicles, 시작일 이력)
  mode = company(회사 차량) / own(자차) / none(차량 없음)
- [S3-P2h-3c] 인력을 못 찾았거나 그 날짜 기준 차량 이력이 없으면 차량 못 찾음(unknown) — 기존 계정 차량 배정(vehicle_assignments)은 읽지 않음 (테이블은 보존)
- 같은 회사 차량·같은 계정을 두 사람이 겹치는 기간에 '이력'으로 쓰는 것은 막는다
  [S3-P2h-3e] 다른 날 시작이면 저장 때 확인 후 앞사람 기간을 끊음(앞사람에게 '없음' 행 추가), 같은 날 시작은 거절
  그날 예외는 그날 계산만 바꾸고 이력 겹침은 풀지 않는다
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
            day_map: dict[tuple[date, int], int | None]) -> dict:
    """계정 mid의 그날 → {worker_id, vehicle_id, basis}.
    owner = 그날 이 계정 담당 인력 (assign_owner 결과, 못 찾으면 None)
    basis = day / company / own / none / unknown(인력을 못 찾았거나 그 날짜 기준 차량 이력 없음)
    [S3-P2h-3c] 기존 계정 차량 배정(legacy) 경로 제거"""
    if owner is not None:
        vid, basis = vehicle_of(hist_by, day_map, owner, d)
        if basis != "no_history":
            return {"worker_id": owner, "vehicle_id": vid, "basis": basis}
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


def disposal_problem(rows: list[dict], ends: dict[int, date | None] | None,
                     disposed: dict[int, date]) -> dict | None:
    """[S3-P2h-3b-2] 처분일(disposed = {차량: 처분일}) 뒤에도 그 차량으로 이어지는 이력 → {worker_id, vehicle_id, disposed_on}. 없으면 None.
    rows = 저장하려는 상태 그대로의 전체 이력 (overlaps와 같은 방식)"""
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


# ---------- [S3-P2h-3e] 계정·차량 공통 기간 규칙 ----------
def hold_spans(rows: list[dict], ends: dict[int, date | None] | None, key: str) -> list[dict]:
    """시작일 이력 → 인력별 기간 [{worker_id, value, start, end}].
    value = 행의 key 값 (회사 차량 id · 계정 id, 차량 없음·자차·계정 없음이면 None).
    end = 다음 이력 전날 (마지막은 None). ends = {인력: 퇴사일} → 퇴사일에서 끝냄, 퇴사 뒤 시작 이력은 무시 (활성 여부 상관없음)"""
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
            v = r.get(key)
            out.append({"worker_id": wid, "value": int(v) if v is not None else None,
                        "start": r["start_date"], "end": end})
    return out


def overlaps(rows: list[dict], ends: dict[int, date | None] | None, key: str, wid: int | None = None) -> list[dict]:
    """같은 값(차량·계정)을 다른 두 인력이 겹치는 기간에 가진 경우 [{value, first, second, from}].
    first = 먼저 시작한 쪽 기간, from = 겹침 시작일. wid를 주면 그 인력이 낀 겹침만.
    rows = 저장하려는 상태 그대로의 전체 이력 (수정 전 행은 빼고 새 행은 넣어서 넘김)"""
    sp = [s for s in hold_spans(rows, ends, key) if s["value"] is not None]
    out = []
    for i, a in enumerate(sp):
        for b in sp[i + 1:]:
            if a["value"] != b["value"] or a["worker_id"] == b["worker_id"] or not _overlap(a, b):
                continue
            if wid is not None and wid not in (a["worker_id"], b["worker_id"]):
                continue
            first, second = sorted((a, b), key=lambda s: (s["start"], s["worker_id"]))
            out.append({"value": a["value"], "first": first, "second": second, "from": second["start"]})
    return out


def handover_cuts(rows: list[dict], ends: dict[int, date | None] | None, key: str, new: dict) -> list[dict]:
    """새 행(new: worker_id, start_date, key 값)이 다른 인력의 '앞서 시작한' 기간에 걸리면 → 그 인력을 새 시작일에 끊는 목록
    [{worker_id, cut_on, value, start}] (cut_on = 앞사람에게 '없음' 행을 넣을 날짜 = 새 시작일).
    같은 날 시작(start == 새 시작일)은 끊지 않음 → overlaps가 거절. rows = 새 행을 넣기 전 상태"""
    v = new.get(key)
    if v is None:
        return []
    d = new["start_date"]
    cuts = []
    for s in hold_spans(rows, ends, key):
        if (s["value"] == int(v) and s["worker_id"] != int(new["worker_id"]) and s["start"] < d
                and (s["end"] is None or d <= s["end"])):
            cuts.append({"worker_id": s["worker_id"], "cut_on": d, "value": s["value"], "start": s["start"]})
    return cuts


# ---------- [S3-P2h-3d-2a] 월별 정합성 표 칸 표시 ----------
BOARD_FLAGS = {"no_worker": "담당 인력 없음", "after_end": "퇴사 뒤 운행", "no_vehicle": "차량 이력 없음",
               "disposed": "처분 뒤 사용", "shared": "공유 차량"}
BOARD_ERRORS = ("no_worker", "after_end", "no_vehicle", "disposed")   # 고쳐야 하는 것 (공유 차량은 확인용)


def board_flags(r: dict, end: date | None, disposed_on: date | None, shared: bool, d: date) -> list[str]:
    """배송이 있던 날 d, 계정 하나의 판정 결과 r = {worker_id, vehicle_id, basis} → 칸 표시 목록.
    end = 담당 인력 퇴사일, disposed_on = 그날 차량 처분일 (처분일 당일까지는 사용 가능), shared = 그날 차량을 다른 계정도 씀"""
    if r.get("worker_id") is None:
        return ["no_worker"]
    out = []
    if end is not None and d > end:
        out.append("after_end")
    elif r.get("basis") == "unknown":
        out.append("no_vehicle")
    if r.get("vehicle_id") and disposed_on is not None and d > disposed_on:
        out.append("disposed")
    if shared:
        out.append("shared")
    return out


# ---------- [S3-P2h-3d-5] 점검 제외 계정 (표시만, 계산에는 영향 없음) ----------
EXCLUDE_REASONS = {"internal": "직원식", "hold": "보류", "other": "기타"}


def check_exclude(reason: str, start: date, end: date | None) -> str | None:
    """점검 제외 저장 전 검사. 문제 없으면 None."""
    if reason not in EXCLUDE_REASONS:
        return "제외 사유를 확인하세요 (직원식 / 보류 / 기타)"
    if end is not None and end < start:
        return "종료일이 시작일보다 빠릅니다"
    return None


def exclude_on(rows: list[dict], mid: int, d: date) -> dict | None:
    """계정 mid가 날짜 d에 점검 제외인 행 (시작일 ≤ d ≤ 종료일, 종료일 비면 계속). 없으면 None."""
    for r in rows:
        if int(r["manager_id"]) == int(mid) and r["start_date"] <= d and (r["end_date"] is None or d <= r["end_date"]):
            return r
    return None


def exclude_overlap(rows: list[dict], mid: int, start: date, end: date | None) -> dict | None:
    """같은 계정의 기존 제외 기간과 겹치면 그 행. 없으면 None."""
    for r in rows:
        if int(r["manager_id"]) != int(mid):
            continue
        if (r["end_date"] is None or start <= r["end_date"]) and (end is None or r["start_date"] <= end):
            return r
    return None
