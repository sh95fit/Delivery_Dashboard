"""S0-P4.8 기간 매출 — 하루 집계(day_aggregate)를 날짜별로 실행해 합산한다.

별도 SQL을 두지 않으므로 기간 합계 = 하루 카드 합계가 항상 성립한다.
(환불 차감 · 취소 제외 · VAT 제외 · 고객사 정책 단가 · 직원식 분리 규칙이 모두 같음)
"""
from __future__ import annotations

from datetime import date as date_type, datetime, timedelta

from app.services import day_aggregate
from app.services.day_aggregate import KST

from concurrent.futures import ThreadPoolExecutor

from app.services import day_cache

MAX_DAYS = 62
PARALLEL = 4

_TOTAL_FIELDS = (
    "stops", "accounts", "meals", "lunch_meals", "dinner_meals",
    "web_qty", "admin_qty", "app_qty", "refund_qty",
    "gross_revenue", "refund_amount", "net_revenue", "estimated_revenue",
    "internal_meals", "internal_net",
)
_MGR_FIELDS = (
    "stops", "meals", "accounts", "lunch_meals", "dinner_meals",
    "gross_revenue", "refund_amount", "net_revenue", "internal_meals", "internal_net",
)
_LU_FIELDS = (
    "qty", "refund_qty", "gross_revenue", "refund_amount", "net_revenue",
    "internal_qty", "internal_net",
)


def _i(v) -> int:
    return int(v or 0)


def combine_days(views: list[dict]) -> dict:
    """delivery_view 결과 여러 날을 합산 (순수 함수 → 단위 테스트 대상).

    stops·accounts는 '일자별 합(연인원)'이다. 기간 중 같은 고객사는 날마다 1번씩 센다.
    """
    total = {k: 0 for k in _TOTAL_FIELDS}
    managers: dict = {}
    lineups: dict = {}
    by_day: list[dict] = []

    for v in views:
        s = v.get("summary") or {}
        for k in _TOTAL_FIELDS:
            total[k] += _i(s.get(k))

        for m in v.get("managers") or []:
            key = m.get("manager_id")
            acc = managers.setdefault(key, {
                "manager_id": key,
                "manager_name": m.get("manager_name"),
                **{f: 0 for f in _MGR_FIELDS},
                "lineups": {},
            })
            acc["manager_name"] = m.get("manager_name") or acc["manager_name"]
            for f in _MGR_FIELDS:
                acc[f] += _i(m.get(f))
            for pid, lu in (m.get("lineups") or {}).items():
                d = acc["lineups"].setdefault(str(pid), {"name": lu.get("name") or str(pid), "qty": 0, "amount": 0})
                d["qty"] += _i(lu.get("qty"))
                d["amount"] += _i(lu.get("amount"))

        for pid, lu in (v.get("by_lineup") or {}).items():
            d = lineups.setdefault(str(pid), {
                "name": lu.get("name") or str(pid),
                "meal": lu.get("meal") or "lunch",
                **{f: 0 for f in _LU_FIELDS},
            })
            for f in _LU_FIELDS:
                d[f] += _i(lu.get(f))

        by_day.append({
            "date": v.get("date"),
            "estimated": bool(v.get("estimated")),
            "stops": _i(s.get("stops")),
            "meals": _i(s.get("meals")),
            "gross_revenue": _i(s.get("gross_revenue")),
            "refund_amount": _i(s.get("refund_amount")),
            "net_revenue": _i(s.get("net_revenue")),
            "internal_net": _i(s.get("internal_net")),
        })

    for d in lineups.values():
        d["amount"] = d["net_revenue"]          # 하위 호환: 기존 amount = 순매출(VAT 제외)

    by_manager = sorted(
        managers.values(),
        key=lambda x: (x["manager_id"] is None, -x["net_revenue"]),   # 미배정은 맨 아래
    )
    return {
        "total": total,
        "by_manager": by_manager,
        "by_lineup": lineups,
        "by_day": by_day,
        "days": len(views),
        "estimated_days": sum(1 for d in by_day if d["estimated"]),
    }


def _views(start: date_type, end: date_type, now: datetime) -> list[dict]:
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    with ThreadPoolExecutor(max_workers=PARALLEL) as ex:
        aggs = list(ex.map(lambda d: day_cache.get_day(d, now), days))
    return [day_aggregate.delivery_view(a) for a in aggs]


def get_revenue_summary(start: date_type, end: date_type) -> dict:
    if end < start:
        raise ValueError("시작일이 종료일보다 늦습니다")
    if (end - start).days + 1 > MAX_DAYS:
        raise ValueError(f"조회 기간은 최대 {MAX_DAYS}일입니다")

    out = combine_days(_views(start, end, datetime.now(KST)))
    out["from_date"] = start.isoformat()
    out["to_date"] = end.isoformat()
    return out