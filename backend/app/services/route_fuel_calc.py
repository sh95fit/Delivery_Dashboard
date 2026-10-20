"""S3-P2b NCP(네이버 길찾기) 예상 유류비 · 직접 계산 — 참고용 순수 함수 (DB 없음 → 단위 테스트 대상).
물류비 합계에는 넣지 않는다 (실제 주유 기록이 기준). 실제와 비교해 연비·경로 이상을 찾는 용도."""
from __future__ import annotations

from bisect import bisect_right
from datetime import date

STATE_RANK = {"RESULT": 0, "COMPLETED_FIXED": 1}   # 실제 달린 경로만. LIVE·REMAINING·PREVIEW는 남은 예정 경로가 섞여 제외


def parse_key(key: str) -> tuple[date, int, str] | None:
    """route_cache.route_key '2026-10-15:12:RESULT:…' → (날짜, 계정, 상태). 형식이 다르면 None."""
    parts = str(key).split(":", 3)
    if len(parts) < 3:
        return None
    try:
        return date.fromisoformat(parts[0]), int(parts[1]), parts[2]
    except ValueError:
        return None


def pick_routes(rows: list[dict]) -> dict[tuple[date, int], dict]:
    """거리 0 경로·예정 경로(LIVE·REMAINING·PREVIEW)는 버리고, (날짜, 계정)마다 RESULT > COMPLETED_FIXED, 같은 상태면 최근 것 하나."""
    best: dict[tuple[date, int], tuple[tuple, dict]] = {}
    for r in rows:
        k = parse_key(r["route_key"])
        if k is None or int(r.get("distance_m") or 0) <= 0:
            continue
        d, mid, state = k
        if state not in STATE_RANK:
            continue        
        ts = r.get("created_at")
        rank = (STATE_RANK.get(state, 9), -(ts.timestamp() if ts else 0))
        cur = best.get((d, mid))
        if cur is None or rank < cur[0]:
            best[(d, mid)] = (rank, r)
    return {k: v[1] for k, v in best.items()}


def price_index(prices: list[dict]) -> dict[str, list[tuple]]:
    """fuel_price_log → 연료별 (날짜, 직접입력 여부, id, 단가) 정렬 목록."""
    idx: dict[str, list[tuple]] = {}
    for p in prices:
        idx.setdefault(p["fuel_type"], []).append(
            (p["price_date"], p.get("source") == "manual", int(p["id"]), float(p["price"])))
    for v in idx.values():
        v.sort()
    return idx


def price_on(idx: dict[str, list[tuple]], fuel_type: str | None, d: date) -> float | None:
    """그날 이전 가장 최근 단가. 같은 날이면 직접 입력 우선 (경로 계산 _vehicle_params와 같은 규칙)."""
    lst = idx.get(fuel_type or "")
    if not lst:
        return None
    i = bisect_right(lst, (d, True, float("inf"), float("inf")))
    return lst[i - 1][3] if i else None


def direct_cost(distance_m: int, km_per_l, price) -> int | None:
    """주행거리 ÷ 연비 × 단가. 거리·연비·단가 중 하나라도 없으면 None."""
    if not distance_m or not km_per_l or not price or float(km_per_l) <= 0:
        return None
    return round(distance_m / 1000 / float(km_per_l) * float(price))
