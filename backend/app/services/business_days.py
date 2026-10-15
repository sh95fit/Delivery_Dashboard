"""S3-P1b-1 영업일 규칙 (DB 없음 → 단위 테스트 대상).
영업일 = 월~토. 일요일·공휴일은 휴무, 대체공휴일은 정상 영업.
규칙과 다른 날(임시공휴일 영업, 특별 휴무 등)은 overrides로 날짜별 지정 → 규칙보다 우선."""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import holidays


@lru_cache(maxsize=64)
def _kr(year: int):
    return holidays.KR(years=year, language="ko")


def rule_closed(d: date) -> str | None:
    """규칙상 휴무면 사유, 영업일이면 None. 같은 날 이름이 여럿이면 '; '로 이어져 있음."""
    if d.weekday() == 6:
        return "일요일"
    name = _kr(d.year).get(d)
    if not name:
        return None
    real = [n.strip() for n in str(name).split(";") if n.strip() and "대체" not in n]
    return ", ".join(real) or None      # 대체공휴일만 있는 날 → 영업


def day_status(d: date, overrides: dict[date, dict]) -> tuple[bool, str | None, str]:
    """(영업 여부, 사유, 근거 'override'|'rule')."""
    o = overrides.get(d)
    if o is not None:
        is_open = bool(o["is_open"])
        return is_open, o.get("memo") or ("지정 영업" if is_open else "지정 휴무"), "override"
    why = rule_closed(d)
    return why is None, why, "rule"


def business_days(frm: date, to: date, overrides: dict[date, dict] | None = None) -> list[date]:
    ov = overrides or {}
    out: list[date] = []
    d = frm
    while d <= to:
        if day_status(d, ov)[0]:
            out.append(d)
        d += timedelta(days=1)
    return out


def split_over(amount: int, days: list[date]) -> dict[date, int]:
    """금액을 날짜 목록에 균등 배분. 나머지 원은 앞 날짜부터 1원씩 → 합계 = amount."""
    amount = int(amount or 0)
    days = sorted(days)
    if not days or amount <= 0:
        return {}
    base, rem = divmod(amount, len(days))
    return {d: base + (1 if i < rem else 0) for i, d in enumerate(days)}
