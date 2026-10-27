"""S3-P2d-2a 실제 경로 구간 계산 — 순수 함수 (DB·네트워크 없음 → 단위 테스트 대상).
완료 시각 순으로 '마지막 연결 지점 → 새로 완료된 곳'만 이어 붙인다."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta

from app.services.day_aggregate import KST, to_kst

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


def preview_input(stops: list[dict], mid: int, origin: dict, skip: set | None = None) -> tuple[dict, list[dict], str]:
    """지도 남은 경로 미리보기 입력. stops = 하루 집계 stops.
    출발 = 마지막 완료 지점(없으면 출발지), 남은 곳 = 미완료 배송지(배송 순서 seq 순).
    sig = 출발 좌표 + 남은 곳 목록 → 바뀌면 미리보기를 다시 계산해야 함."""
    done, rem = [], []
    for s in stops:
        if not s.get("has_coord") or s.get("manager_id") is None or int(s["manager_id"]) != mid:
            continue
        if s.get("cancelled"):
            continue                                   # [S3-P2f] 배송 취소 → 남은 경로·출발점에서 뺌        
        if skip and s.get("address_id") is not None and int(s["address_id"]) in skip:
            continue                                   # [S3-P2d-5] 관제 제외 배송지 → 남은 경로·출발점에서 뺌        
        p = {"id": str(s.get("delivery_id") or s.get("address_id")), "lat": float(s["latitude"]), "lng": float(s["longitude"])}
        at = to_kst(s.get("delivered_at"))
        if at:
            done.append((at, p["id"], p))
        else:
            seq = s.get("seq")
            rem.append((seq is None, seq or 0, p["id"], p))
    start = max(done, key=lambda x: (x[0], x[1]))[2] if done else origin
    left = [x[3] for x in sorted(rem, key=lambda x: x[:3])]
    raw = f'{start["lat"]:.6f},{start["lng"]:.6f}|' + ",".join(p["id"] for p in left)
    return start, left, hashlib.sha1(raw.encode()).hexdigest()[:12]


# ---------- S3-P2d-4 관제: 남은 경로 예상 도착 · 지연 예상 · 정체 (순수 함수) ----------
DEFAULT_DWELL_MS = 300_000                       # 정차 시간 기본 5분 (완료 3곳 미만이라 중앙값을 못 구할 때)
DWELL_MIN_MS, DWELL_MAX_MS = 60_000, 1_200_000   # 정차 시간은 1~20분으로 제한


def target_at(d: date, hhmm: str | None) -> datetime | None:
    """고객 희망 시각 'HH:MM' → 그날 KST 시각. 없거나 못 읽으면 None (= 미지정 고객사)."""
    if not hhmm:
        return None
    try:
        h, m = (int(x) for x in str(hhmm).split(":")[:2])
        return datetime.combine(d, time(h, m), tzinfo=KST)
    except (TypeError, ValueError):
        return None


def dwell_ms(done: list[tuple[datetime, int]]) -> int:
    """done = [(완료 시각, 그 지점까지 주행 시간 ms)] 완료 순.
    1곳당 정차 시간 = (완료 간격 − 그 구간 주행 시간)의 중앙값 → 휴식·상차 한 번에 흔들리지 않음."""
    if len(done) < 3:
        return DEFAULT_DWELL_MS
    gaps = sorted((b[0] - a[0]).total_seconds() * 1000 - b[1] for a, b in zip(done, done[1:]))
    n = len(gaps)
    v = int(gaps[n // 2] if n % 2 else (gaps[n // 2 - 1] + gaps[n // 2]) / 2)
    return max(DWELL_MIN_MS, min(DWELL_MAX_MS, v))


def stop_dwells(done: list[tuple[str, datetime]], leg_ms: dict[str, int]) -> dict[str, int | None]:
    """[S3-P2d-5c] 배송지별 정차 시간(추정, ms). done = [(배송지, 완료 시각)] 완료 순,
    leg_ms = {배송지: 직전 지점 → 그곳 주행 ms} (같은 좌표 묶음의 나머지 곳은 0).
    그곳 정차 = (직전 완료 → 그곳 완료 간격) − 그 구간 주행 시간 (dwell_ms 중앙값과 같은 기준). 첫 곳 None, 음수는 0."""
    out: dict[str, int | None] = {}
    prev = None
    for sid, at in done:
        out[sid] = None if prev is None else max(0, int((at - prev).total_seconds() * 1000) - int(leg_ms.get(sid, 0)))
        prev = at
    return out


LATE_MIN = 1      # 1분 이상 늦으면 지연 예상 (제때 완료되면 사라짐)


def delay_min(at: datetime | None, target: datetime | None) -> int | None:
    """희망 시각 대비 분 (내림). 양수 = 지연, 0 = 1분 미만(정시로 봄), 음수 = 여유. 둘 중 하나 없으면 None."""
    if at is None or target is None:
        return None
    return int((at - target).total_seconds() // 60)


def control_summary(groups: list[dict], rem_ids: list[str], last_at: datetime | None, dwell: int, now: datetime,
                    target_of: dict, stall_min: int, live: bool) -> dict:
    """노선 1개 관제 요약 (S3-P2d-4b).
    groups = 마지막 남은 경로 계산의 묶음 [{ids, distance_m, duration_ms, skipped?}] (배송 순서)
    rem_ids = 지금 남은 배송지(좌표 있는 곳), target_of = {배송지: 희망 시각 | None}
    - 예상 도착: 마지막 완료 + (정차 + 다음 곳 주행) 반복. 첫 곳 예상이 이미 지났으면 지금 도착으로 보고 뒤 곳도 함께 미룸
    - 계산 뒤 완료된 곳은 빼고 셈 → 15분 사이에도 호출 없이 갱신
    - 지연 예상: 희망 시각보다 1분 이상 늦은 곳 (배송지별 delay_min)
    - 정체: 다음 곳 예상 도착보다 stall_min분 넘게 지났는데 새 완료 없음
      단, 지금 출발해도 다음 곳 희망 시각에 맞출 수 있으면 '대기' (희망 시각에 맞춰 기다리는 경우)"""
    rem = set(rem_ids)
    eta: dict = {}
    skipped: set = set()
    t, first, dist, drive = last_at or now, True, 0, 0
    next_eta, next_id, next_leg = None, None, 0
    for g in groups:
        ids = [i for i in (g.get("ids") or []) if i in rem]
        if not ids:
            continue
        if g.get("skipped"):
            skipped.update(ids)
            continue
        leg = int(g.get("duration_ms") or 0)
        wait = dwell if (last_at is not None or not first) else 0
        t = t + timedelta(milliseconds=wait + leg)
        if first:
            next_eta, next_id, next_leg = t, ids[0], leg
            t = max(t, now)
            first = False
        dist += int(g.get("distance_m") or 0)
        drive += leg
        for i in ids:
            eta[i] = t
    stops = [{"id": i, "target_at": target_of[i].isoformat() if target_of.get(i) else None,
              "eta": eta[i].isoformat() if i in eta else None,
              "delay_min": delay_min(eta.get(i), target_of.get(i)), "skipped": i in skipped} for i in rem_ids]
    late = [s for s in stops if live and s["delay_min"] is not None and s["delay_min"] >= LATE_MIN]   # [S3-P2d-5] 지연 예상은 오늘(진행 중)만
    no_time = [i for i in rem_ids if not target_of.get(i)]
    uncalc = [i for i in rem_ids if i not in eta and i not in skipped]
    idle = int((now - last_at).total_seconds() // 60) if last_at else None
    behind = delay_min(now, next_eta) if last_at else None
    if not rem_ids:
        state = "done"
    elif not live:
        state = "incomplete"
    elif last_at is None:
        state = "before"
    elif behind is not None and behind >= stall_min:
        tg = target_of.get(next_id)
        state = "wait" if tg and now + timedelta(milliseconds=next_leg) <= tg else "stalled"
    elif late:
        state = "late"
    else:
        state = "ok"
    return {"state": state, "remaining": len(rem_ids), "remaining_m": dist, "remaining_drive_ms": drive,
            "finish_at": max(eta.values()).isoformat() if eta else None,
            "next_eta": next_eta.isoformat() if next_eta else None, "behind_min": behind,
            "stops": stops, "late": late, "max_delay_min": max((s["delay_min"] for s in late), default=0),
            "no_time_ids": no_time, "uncalc_n": len(uncalc), "skipped_n": len(skipped),
            "last_at": last_at.isoformat() if last_at else None, "idle_min": idle,
            "dwell_min": round(dwell / 60000, 1)}


def trim_preview(last: dict | None, rem: set) -> dict | None:
    """[S3-P2d-5] 남은 경로 점선에서 이미 완료된 곳까지의 선을 지움 (NAVER 호출 없음).
    묶음별 선(groups[].path)이 있는 계산만 다듬고, 예전 계산은 다음 재계산까지 그대로.
    화면 응답에는 묶음별 선을 빼서 가볍게 보낸다."""
    if not last or not any("path" in g for g in last.get("groups") or []):
        return last
    path: list = []
    for g in last["groups"]:
        if g.get("skipped") or not any(i in rem for i in g.get("ids") or []):
            continue
        pts = g.get("path") or []
        path.extend(pts[1:] if path and pts else pts)
    return {**last, "path": path, "groups": [{k: v for k, v in g.items() if k != "path"} for g in last["groups"]]}
