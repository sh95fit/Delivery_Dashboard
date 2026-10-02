"""S1-P1 비용 계산 순수 함수 (DB 없음 → 단위 테스트 대상)."""
from __future__ import annotations

from datetime import date


def days_incl(start: date, end: date) -> int:
    return (end - start).days + 1


def allocate_period(amount: int, start: date, end: date, frm: date, to: date) -> int:
    """기간 비용(start~end)을 일 단위로 나눠 [frm, to] 구간 몫을 돌려준다.
    나머지 원은 앞쪽 날짜부터 1원씩 → 전체 기간을 어떻게 쪼개 더해도 합계 = amount."""
    total = days_incl(start, end)
    amount = int(amount or 0)
    if total <= 0 or amount <= 0:
        return 0
    lo, hi = max(start, frm), min(end, to)
    if hi < lo:
        return 0
    base, rem = divmod(amount, total)
    i0, i1 = (lo - start).days, (hi - start).days
    extra = max(0, min(rem, i1 + 1) - i0)
    return base * (i1 - i0 + 1) + extra


def effective_on(rows: list[dict], day: date, field: str) -> dict | None:
    """시작일(field) <= day 인 행 중 가장 최근 것 = 그 날 적용되는 값."""
    best = None
    for r in rows:
        d = r[field]
        if d <= day and (best is None or d > best[field]):
            best = r
    return best


def latest_by(rows: list[dict], key: str, field: str, day: date) -> dict:
    """key(예: manager_id)별로 day에 적용되는 행."""
    groups: dict = {}
    for r in rows:
        groups.setdefault(r[key], []).append(r)
    out = {}
    for k, g in groups.items():
        r = effective_on(g, day, field)
        if r is not None:
            out[k] = r
    return out
