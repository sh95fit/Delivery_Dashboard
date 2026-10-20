"""S3-P2d-2a 실제 경로 구간 계산 — 순수 함수 (DB·네트워크 없음 → 단위 테스트 대상).
완료 시각 순으로 '마지막 연결 지점 → 새로 완료된 곳'만 이어 붙인다."""
from __future__ import annotations

D5_MAX_NODES = 6     # Directions 5: 경유지 5 + 도착 1 → 1회 최대 6구간 (경유 6개는 HTTP 400 확인)


def coord_key(lat, lng) -> tuple[float, float]:
    return (round(float(lat), 6), round(float(lng), 6))


def pending_groups(stops: list[dict], done_ids: set, last_coord: tuple) -> tuple[list[str], list[dict]]:
    """stops = [{id, lat, lng, at}] 완료된 배송지, done_ids = 이미 구간에 들어간 id, last_coord = 마지막 연결 지점 좌표.
    반환 (merge_ids, groups)
    - merge_ids: 마지막 연결 지점과 같은 좌표 → 호출 없이 그 구간에 붙임
    - groups: [{ids, lat, lng, at}] 완료 시각 순, 연속으로 같은 좌표는 하나로"""
    todo = sorted((s for s in stops if s["id"] not in done_ids), key=lambda s: (s["at"], s["id"]))
    merge: list[str] = []
    groups: list[dict] = []
    for s in todo:
        k = coord_key(s["lat"], s["lng"])
        if groups and k == coord_key(groups[-1]["lat"], groups[-1]["lng"]):
            groups[-1]["ids"].append(s["id"])
        elif not groups and k == last_coord:
            merge.append(s["id"])
        else:
            groups.append({"ids": [s["id"]], "lat": s["lat"], "lng": s["lng"], "at": s["at"]})
    return merge, groups


def chunks(groups: list[dict], size: int = D5_MAX_NODES) -> list[list[dict]]:
    return [groups[i:i + size] for i in range(0, len(groups), size)]


def split_legs(route: dict | None, n: int) -> list[dict] | None:
    """D5 응답 route.trafast[0] → 구간 n개 [{distance_m, duration_ms, path}].
    경유(87)·도착(88) 안내에서 끊는다. 구간 수가 n과 다르면 None (저장하지 않음)."""
    if not route:
        return None
    path = route.get("path") or []
    s = route.get("summary") or {}
    legs: list[dict] = []
    dist = dur = start = 0
    for g in route.get("guide") or []:
        dist += int(g.get("distance") or 0)
        dur += int(g.get("duration") or 0)
        if g.get("type") in (87, 88):
            end = int(g.get("pointIndex") or 0)
            legs.append({"distance_m": dist, "duration_ms": dur, "path": path[start:end + 1]})
            dist = dur = 0
            start = end
    if not legs and n == 1 and s.get("distance"):
        return [{"distance_m": int(s["distance"]), "duration_ms": int(s.get("duration") or 0), "path": path}]
    if len(legs) != n:
        return None
    if s.get("distance"):
        legs[-1]["distance_m"] += int(s["distance"]) - sum(x["distance_m"] for x in legs)
    return legs


def alloc(total, weights: list[int]) -> list[int]:
    """호출 1회 합계(유류비·통행료)를 구간 거리 비율로 나눔. 합계 보존 (나머지는 마지막 구간)."""
    if not weights:
        return []
    total = int(total or 0)
    w = sum(weights)
    if w <= 0 or total == 0:
        return [0] * (len(weights) - 1) + [total]
    out = [total * x // w for x in weights]
    out[-1] += total - sum(out)
    return out


def d5_code(status: int, body: dict) -> int | None:
    """D5 응답 → NAVER code. 정상(HTTP 200)은 body.code, 길찾기 결과 오류(HTTP 400: 출발=도착 1, 도로와 멂 2 등)는
    body.error.code. 인증·서버 오류 등 판단할 수 없으면 None."""
    if status == 200:
        c = body.get("code")
    elif status == 400 and isinstance(body.get("error"), dict):
        c = body["error"].get("code")
    else:
        c = None
    try:
        return int(c) if c is not None else None
    except (TypeError, ValueError):
        return None
