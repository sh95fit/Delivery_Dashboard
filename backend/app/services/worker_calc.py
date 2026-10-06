"""S2-P0 인력·계정 연결, 월 급여·초과수당·부가세 순수 함수 (DB 없음 → 단위 테스트 대상).
급여 규칙(2026-09 근무표 검증): 기본급 = 시급 × 월 실제 근무 분 ÷ 60, 반올림은 월 합계에서 1회.
"""
from __future__ import annotations

from datetime import time


def minutes_between(clock_in: time | None, clock_out: time | None) -> int:
    """출근~퇴근 분. 값이 없거나 퇴근 ≤ 출근이면 0 (자정 넘김 미지원)."""
    if clock_in is None or clock_out is None:
        return 0
    m = (clock_out.hour * 60 + clock_out.minute) - (clock_in.hour * 60 + clock_in.minute)
    return max(0, m)


def worked_paid_minutes(clock_in: time | None, clock_out: time | None, break_min: int, break_paid: bool) -> int:
    """실제 유급 근무 분. 무급 휴게만 뺀다."""
    span = minutes_between(clock_in, clock_out)
    return span if break_paid else max(0, span - int(break_min or 0))


def overtime_minutes(actual_paid: int, base_paid: int) -> int:
    """하루 초과 분 = 실제 유급 분 − 기본 유급 분 (음수면 0)."""
    return max(0, int(actual_paid or 0) - int(base_paid or 0))


def overtime_pay(ot_min: int, unit_min: int, unit_amount: int) -> int:
    """초과수당 = 단위(분)마다 지정 금액, 단위 미만 버림. 단위 0 = 초과수당 없음."""
    if unit_min <= 0 or unit_amount <= 0 or ot_min <= 0:
        return 0
    return (int(ot_min) // int(unit_min)) * int(unit_amount)


def month_base_pay(entries: list[tuple[int, int]]) -> int:
    """entries = [(유급 분, 시급), ...]. 월 중 시급 변경도 합산 후 1회 반올림 (엑셀과 동일)."""
    total = sum(int(m) * int(r) for m, r in entries)
    return (total + 30) // 60


def vat_of(amount: int, applied: bool) -> int:
    """부가세 10%, 원 단위 반올림."""
    return (int(amount) + 5) // 10 if applied else 0


def resolve_accounts(fixed: dict[int, int | None], overrides: dict[int, int | None]) -> dict[int, int]:
    """그날 계정별 사용자.
    fixed     = {worker_id: 고정 manager_id}
    overrides = {manager_id: worker_id | None}  (그날 예외, None = 그날 계정 미사용)
    반환      = {manager_id: worker_id}. 예외로 다른 계정에 간 사람의 원래 계정은 그날 비운다."""
    acc = {mid: wid for wid, mid in fixed.items() if mid is not None}
    moved = {w for w in overrides.values() if w is not None}
    acc = {m: w for m, w in acc.items() if w not in moved}
    for mid, wid in overrides.items():
        if wid is None:
            acc.pop(mid, None)
        else:
            acc[mid] = wid
    return acc
