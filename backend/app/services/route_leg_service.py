"""S3-P2d-2a 실제 경로 구간 누적 (NAVER Directions 5).
- 작업자가 3분마다 계정별로 '마지막 연결 지점 → 새로 완료된 곳'만 계산해 route_legs에 저장
- 저장한 구간은 다시 계산하지 않는다 → 같은 구간 중복 호출 없음, 새 완료가 없으면 호출 0
- ROUTE_LEGS_MODE=live 일 때만 호출 (NAVER_MODE와 별개 — 기존 경로 엔진(Directions 15)은 계속 꺼 둔다)
- 호출 수는 naver_call_log(DB)에 기록 → 재시작·여러 프로세스에도 정확
- 지난 날짜 채우기: python -m app.services.route_leg_service 2026-10-19 2026-10-16"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime

import requests
from sqlalchemy import text

from app.database import get_dash_engine
from app.services import control_exclude_service, dash_db, day_cache, routes_service
from app.services.day_aggregate import KST, to_kst
from app.services.route_leg_calc import (alloc, chunks, control_summary, coord_key, d5_code, delay_min, dwell_ms,
                                         pending_groups, preview_input, split_legs, target_at, trim_preview)

logger = logging.getLogger("route_legs")

D5_URL = "https://maps.apigw.ntruss.com/map-direction/v1/driving"
API = "d5"
DAILY_LIMIT = int(os.environ.get("ROUTE_DAILY_LIMIT", "1500"))
MONTHLY_LIMIT = int(os.environ.get("ROUTE_MONTHLY_LIMIT", "55000"))
BACKFILL_RESERVE = 500          # 지난 날짜 채우기는 하루 한도에서 500회를 남기고 멈춤 (당일 경로 우선)
UNREACHABLE = (2, 3, 4, 5)      # 도로와 너무 멂·자동차 길 없음 등 → 그 지점만 '연결 불가'
PREVIEW_RESERVE = 300           # 지도 미리보기는 하루 한도에서 300회를 남기고 막음 (당일 실제 경로 우선)
PREVIEW_TTL = 21600             # 미리보기 결과 보관 6시간 (Redis)
PREVIEW_WORKERS = 4             # 전체 노선 미리보기: 4명씩 동시에 계산
ETA_EVERY = int(os.environ.get("ETA_INTERVAL_MIN", "15")) * 60   # [S3-P2d-4] 남은 경로 자동 재계산 주기(초) — 출발한 노선만
STALL_MIN = int(os.environ.get("ETA_STALL_MIN", "15"))          # [S3-P2d-4b] 정체 = 다음 곳 예상 도착보다 15분 넘게 지났는데 새 완료 없음

_INS = text("""INSERT INTO route_legs (route_date, manager_id, seq, from_lat, from_lng, to_lat, to_lng, to_stop_ids,
        delivered_at, status, error_code, distance_m, duration_ms, fuel_price_naver, toll_fare, ncp_mileage, path, purpose)
    VALUES (:d, :m, :seq, :flat, :flng, :tlat, :tlng, :ids, :at, :status, :code, :dist, :dur, :fuel, :toll, :mil,
        CAST(:path AS jsonb), :purpose)
    ON CONFLICT (route_date, manager_id, seq) DO NOTHING""")


class StopCalls(Exception):
    """호출 꺼짐·한도 도달 → 이번 주기 중단 (다음 주기에 이어서)."""


def enabled() -> bool:
    return os.environ.get("ROUTE_LEGS_MODE", "off").strip() == "live"


def calls_used(d: date) -> tuple[int, int]:
    """(그날 호출 수, 그달 1일~그날 호출 수)"""
    r = dash_db.rows("""SELECT COALESCE(SUM(n) FILTER (WHERE call_date = :d), 0) AS day, COALESCE(SUM(n), 0) AS month
        FROM naver_call_log WHERE api = :api AND call_date >= :m AND call_date <= :d""",
                     {"d": d, "m": d.replace(day=1), "api": API})[0]
    return int(r["day"]), int(r["month"])


def _take_call(purpose: str) -> None:
    today = datetime.now(KST).date()
    day, month = calls_used(today)
    limit = DAILY_LIMIT - {"backfill": BACKFILL_RESERVE, "preview": PREVIEW_RESERVE, "eta": PREVIEW_RESERVE}.get(purpose, 0)
    if day >= limit or month >= MONTHLY_LIMIT:
        raise StopCalls(f"NAVER 호출 한도 도달 (오늘 {day}/{limit}, 이번 달 {month}/{MONTHLY_LIMIT})")
    with get_dash_engine().begin() as c:
        c.execute(text("""INSERT INTO naver_call_log (call_date, api, purpose, n) VALUES (:d, :api, :p, 1)
            ON CONFLICT (call_date, api, purpose) DO UPDATE SET n = naver_call_log.n + 1"""),
                  {"d": today, "api": API, "p": purpose})


def _d5(start: dict, nodes: list[dict], vparams: dict, purpose: str) -> tuple[int, dict | None]:
    """start → nodes(마지막 = 도착, 나머지 = 경유). 반환 (NAVER code, route|None). HTTP 오류는 예외."""
    if not enabled():
        raise StopCalls("ROUTE_LEGS_MODE가 live가 아니라 NAVER를 호출하지 않습니다")
    _take_call(purpose)
    ll = lambda p: f'{p["lng"]},{p["lat"]}'  # noqa: E731
    params = {"start": ll(start), "goal": ll(nodes[-1]), "option": "trafast", **vparams}
    if len(nodes) > 1:
        params["waypoints"] = "|".join(ll(p) for p in nodes[:-1])
    headers = {"x-ncp-apigw-api-key-id": os.environ.get("NAVER_MAPS_API_KEY_ID", ""),
               "x-ncp-apigw-api-key": os.environ.get("NAVER_MAPS_API_KEY", "")}
    r = requests.get(D5_URL, params=params, headers=headers, timeout=15)
    try:
        j = r.json()
    except ValueError:
        j = {}
    j = j if isinstance(j, dict) else {}
    code = d5_code(r.status_code, j)    # 출발=도착(1)·도로와 멂(2) 등은 HTTP 400으로 옴 → 코드로 받아 지점별 처리
    if code is None:
        raise RuntimeError(f"NAVER HTTP {r.status_code}: {r.text[:200]}")
    route = ((j.get("route") or {}).get("trafast") or [None])[0] if code == 0 else None
    return code, route


def _row(d, mid, seq, frm, g, purpose, status="ok", code=None, leg=None, fuel=0, toll=0, mileage=None) -> dict:
    leg = leg or {}
    return {"d": d, "m": mid, "seq": seq, "flat": frm["lat"], "flng": frm["lng"], "tlat": g["lat"], "tlng": g["lng"],
            "ids": g["ids"], "at": g["at"], "status": status, "code": code,
            "dist": int(leg.get("distance_m") or 0), "dur": int(leg.get("duration_ms") or 0),
            "fuel": int(fuel or 0), "toll": int(toll or 0), "mil": mileage,
            "path": json.dumps(leg["path"]) if leg.get("path") else None, "purpose": purpose}


def _save(rows: list[dict]) -> None:
    if rows:
        with get_dash_engine().begin() as c:
            c.execute(_INS, rows)


def _manager_legs(d: date, mid: int, stops: list[dict], origin: dict, vparams: dict, purpose: str) -> dict:
    out = {"calls": 0, "legs": 0, "unreachable": 0}
    done_rows = dash_db.rows("""SELECT seq, to_lat, to_lng, to_stop_ids, status FROM route_legs
        WHERE route_date = :d AND manager_id = :m ORDER BY seq""", {"d": d, "m": mid})
    done = {x for r in done_rows for x in (r["to_stop_ids"] or [])}
    linked = [r for r in done_rows if r["status"] != "unreachable"]
    cur = {"lat": float(linked[-1]["to_lat"]), "lng": float(linked[-1]["to_lng"])} if linked else origin
    seq = done_rows[-1]["seq"] if done_rows else 0
    merge, groups = pending_groups(stops, done, coord_key(cur["lat"], cur["lng"]))
    mileage = vparams.get("mileage")

    if merge:     # 마지막 지점과 같은 좌표 → 호출 없이 붙임
        if linked:
            with get_dash_engine().begin() as c:
                c.execute(text("""UPDATE route_legs SET to_stop_ids = to_stop_ids || CAST(:ids AS text[])
                    WHERE route_date = :d AND manager_id = :m AND seq = :s"""),
                          {"ids": merge, "d": d, "m": mid, "s": linked[-1]["seq"]})
        else:
            seq += 1
            _save([_row(d, mid, seq, cur, {**cur, "ids": merge, "at": None}, purpose, status="same")])

    for ch in chunks(groups):
        code, route = _d5(cur, ch, vparams, purpose)
        out["calls"] += 1
        legs = split_legs(route, len(ch))
        if legs:
            s = route.get("summary") or {}
            w = [x["distance_m"] for x in legs]
            fuel, toll = alloc(s.get("fuelPrice"), w), alloc(s.get("tollFare"), w)
            rows, prev = [], cur
            for i, (g, leg) in enumerate(zip(ch, legs)):
                seq += 1
                rows.append(_row(d, mid, seq, prev, g, purpose, leg=leg, fuel=fuel[i], toll=toll[i], mileage=mileage))
                prev = g
            _save(rows)
            out["legs"] += len(rows)
            cur = ch[-1]
            continue
        if code not in (0, 1, *UNREACHABLE):
            logger.warning("route legs %s 계정 %s: NAVER code %s — 다음 주기에 다시", d, mid, code)
            return out
        # 묶음 실패 → 한 지점씩 다시 계산해 문제 지점만 '연결 불가'
        for g in ch:
            if len(ch) == 1:
                c1, r1 = code, route
            else:
                c1, r1 = _d5(cur, [g], vparams, purpose)
                out["calls"] += 1
            l1 = split_legs(r1, 1)
            if l1:
                s = r1.get("summary") or {}
                seq += 1
                _save([_row(d, mid, seq, cur, g, purpose, leg=l1[0], fuel=s.get("fuelPrice"),
                            toll=s.get("tollFare"), mileage=mileage)])
                out["legs"] += 1
                cur = g
            elif c1 == 1:          # 출발 = 도착 (같은 자리)
                seq += 1
                _save([_row(d, mid, seq, cur, g, purpose, status="same", code=1)])
                cur = g
            elif c1 in UNREACHABLE or c1 == 0:
                seq += 1
                _save([_row(d, mid, seq, cur, g, purpose, status="unreachable", code=c1)])
                out["unreachable"] += 1
            else:
                logger.warning("route legs %s 계정 %s: NAVER code %s — 다음 주기에 다시", d, mid, c1)
                return out
    return out


def collect(d: date, purpose: str = "legs") -> dict:
    """그날 완료된 배송지 중 아직 구간에 없는 곳만 이어 붙임. 반환 = 요약."""
    out = {"date": d.isoformat(), "managers": 0, "calls": 0, "legs": 0, "unreachable": 0}
    if not enabled():
        out["stopped"] = "ROUTE_LEGS_MODE 꺼짐"
        return out
    agg = day_cache.get_day(d)
    by: dict[int, list[dict]] = {}
    for s in agg.get("stops") or []:
        if not s.get("has_coord") or s.get("manager_id") is None:
            continue
        at = to_kst(s.get("delivered_at"))
        if at:
            by.setdefault(int(s["manager_id"]), []).append(
                {"id": str(s["delivery_id"]), "lat": float(s["latitude"]), "lng": float(s["longitude"]), "at": at})
    o, _ = routes_service._active_origin()
    origin = {"lat": float(o["latitude"]), "lng": float(o["longitude"])}
    for mid, stops in sorted(by.items()):
        try:
            r = _manager_legs(d, mid, stops, origin, routes_service._vehicle_params(d, mid), purpose)
        except StopCalls as e:
            out["stopped"] = str(e)
            break
        except Exception:  # noqa: BLE001
            logger.exception("route legs %s 계정 %s 실패 — 다음 주기에 다시", d, mid)
            continue
        out["managers"] += 1
        for k in ("calls", "legs", "unreachable"):
            out[k] += r[k]
    return out


# ---------- S3-P2d-2b-1 지도: 실제 경로(실선) 조회 · 남은 경로 미리보기(점선, 버튼으로만 계산) ----------
def _origin() -> dict:
    o, _ = routes_service._active_origin()
    return {"lat": float(o["latitude"]), "lng": float(o["longitude"])}


def _jget(key: str):
    try:
        raw = day_cache._redis().get(key)
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        return None


def _jset(key: str, value, ttl: int = PREVIEW_TTL) -> None:
    try:
        day_cache._redis().setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
    except Exception:  # noqa: BLE001
        logger.warning("redis set 실패 (미리보기)", exc_info=True)


def _pkey(d: date, mid: int) -> str:
    return f"route:preview:v1:{d.isoformat()}:{mid}"


def _all_key(d: date) -> str:
    return f"route:preview_all:v1:{d.isoformat()}"


def legs_view(d: date) -> dict:
    """지도용: 계정별 실제 경로 구간(실선) + 마지막 미리보기(점선, 있을 때만). NAVER 호출 없음."""
    rows = dash_db.rows("""SELECT manager_id, seq, status, distance_m, duration_ms, fuel_price_naver, to_stop_ids,
            delivered_at, path FROM route_legs WHERE route_date = :d ORDER BY manager_id, seq""", {"d": d})
    stops = day_cache.get_day(d).get("stops") or []
    origin = _origin()
    mids = {int(r["manager_id"]) for r in rows} | {int(s["manager_id"]) for s in stops if s.get("manager_id") is not None}
    out = {m: {"manager_id": m, "legs": [], "distance_m": 0, "duration_ms": 0, "fuel_price_naver": 0,
               "stops": 0, "unreachable": 0} for m in mids}
    for r in rows:
        m = out[int(r["manager_id"])]
        m["legs"].append({"seq": r["seq"], "status": r["status"], "distance_m": r["distance_m"],
                          "duration_ms": r["duration_ms"], "stop_ids": r["to_stop_ids"] or [],
                          "delivered_at": r["delivered_at"], "path": r["path"] or []})
        m["distance_m"] += int(r["distance_m"] or 0)
        m["duration_ms"] += int(r["duration_ms"] or 0)
        m["fuel_price_naver"] += int(r["fuel_price_naver"] or 0)
        m["stops"] += len(r["to_stop_ids"] or [])
        m["unreachable"] += 1 if r["status"] == "unreachable" else 0
    now = datetime.now(KST)
    skip = control_exclude_service.active_ids()     # [S3-P2d-5] 관제 제외 배송지
    for mid, m in out.items():
        _, left, sig = preview_input(stops, mid, origin, skip)
        last = _jget(_pkey(d, mid)) if left else None
        rem_ids = [p["id"] for p in left]
        m["remaining_stops"] = len(left)
        m["preview_sig"] = sig if left else None
        m["preview"] = trim_preview(last, set(rem_ids))   # [S3-P2d-5] 완료된 곳까지의 점선은 바로 지움
        m["control"] = _control(d, mid, m["legs"], stops, last, rem_ids, now, skip)
        m["preview_stale"] = bool(last) and m["control"]["uncalc_n"] > 0   # 계산 뒤 새로 배정된 곳이 있을 때만 '반영 필요'
    today = now.date()
    return {"date": d.isoformat(), "origin": origin, "enabled": enabled(), "calls_today": calls_used(today)[0],
            "daily_limit": DAILY_LIMIT, "stall_min": STALL_MIN, "eta_every_min": ETA_EVERY // 60,
            "excludes": control_exclude_service.list_items(),
            "managers": [out[m] for m in sorted(out)]}


def _age_sec(last: dict | None) -> float | None:
    try:
        return (datetime.now(KST) - datetime.fromisoformat(last["calc_at"])).total_seconds()
    except (TypeError, KeyError, ValueError):
        return None


def preview(d: date, mid: int, purpose: str = "preview", every: int | None = None) -> dict:
    """남은 경로: 마지막 완료 지점 → 남은 배송지(배송 순서). 저장하지 않음(물류비 미반영).
    - 버튼(every 없음): 같은 상태(sig)면 다시 호출하지 않음
    - [S3-P2d-4] 자동(every=초): 마지막 계산 후 every초 안이면 상태가 바뀌어도 다시 호출하지 않음
      (그 사이 완료된 곳은 관제 화면에서 빼고 계산)
    - groups = 배송지 묶음별 주행 거리·시간 → 예상 도착·지연 판단에 사용"""
    start, left, sig = preview_input(day_cache.get_day(d).get("stops") or [], mid, _origin(),
                                     control_exclude_service.active_ids())
    base = {"manager_id": mid, "sig": sig, "stops": len(left)}
    if not left:
        return {**base, "path": [], "groups": [], "distance_m": 0, "duration_ms": 0, "skipped": 0, "calls": 0,
                "cached": False}
    last = _jget(_pkey(d, mid))
    if last:
        age = _age_sec(last)
        fresh = ("groups" in last and age is not None and age < every) if every else last.get("sig") == sig
        if fresh:
            return {**last, "calls": 0, "cached": True}
    merge, groups = pending_groups([{**p, "at": i} for i, p in enumerate(left)], set(),
                                   coord_key(start["lat"], start["lng"]))
    vparams = routes_service._vehicle_params(d, mid)
    path: list = []
    plan: list[dict] = [{"ids": merge, "distance_m": 0, "duration_ms": 0}] if merge else []
    tot = {"distance_m": 0, "duration_ms": 0, "calls": 0, "skipped": 0}

    def add(route: dict, gs: list[dict]) -> None:
        s = route.get("summary") or {}
        path.extend(route.get("path") or [])
        tot["distance_m"] += int(s.get("distance") or 0)
        tot["duration_ms"] += int(s.get("duration") or 0)
        legs = split_legs(route, len(gs))
        if not legs:        # 구간 나누기 실패 → 묶음 합계를 곳 수대로 나눔 (선은 묶음 마지막 곳에 통째로)
            ones = [1] * len(gs)
            legs = [{"distance_m": a, "duration_ms": b, "path": []}
                    for a, b in zip(alloc(s.get("distance"), ones), alloc(s.get("duration"), ones))]
            legs[-1]["path"] = route.get("path") or []
        for g, leg in zip(gs, legs):
            plan.append({"ids": g["ids"], "distance_m": int(leg["distance_m"]), "duration_ms": int(leg["duration_ms"]),
                         "path": leg.get("path") or []})   # [S3-P2d-5] 묶음별 선 → 완료된 곳 점선은 조회 때 지움

    cur = start
    for ch in chunks(groups):
        code, route = _d5(cur, ch, vparams, purpose)
        tot["calls"] += 1
        if route:
            add(route, ch)
            cur = ch[-1]
            continue
        if code not in (0, 1, *UNREACHABLE):
            raise RuntimeError(f"NAVER code {code}")
        for g in ch:        # 묶음 실패 → 한 곳씩, 문제 지점은 건너뜀
            if len(ch) == 1:
                c1, r1 = code, route
            else:
                c1, r1 = _d5(cur, [g], vparams, purpose)
                tot["calls"] += 1
            if r1:
                add(r1, [g])
                cur = g
            elif c1 == 1:
                plan.append({"ids": g["ids"], "distance_m": 0, "duration_ms": 0})
                cur = g
            else:
                plan.append({"ids": g["ids"], "skipped": True})
                tot["skipped"] += len(g["ids"])
    out = {**base, **tot, "path": path, "groups": plan, "cached": False, "purpose": purpose,
           "calc_at": datetime.now(KST).isoformat()}
    _jset(_pkey(d, mid), out)
    return out


def auto_eta(d: date) -> dict:
    """[S3-P2d-4] 작업자가 배송 시간대에 호출: 출발한(완료 1곳 이상) 노선 중 남은 곳이 있는 노선만
    ETA_EVERY초마다 남은 경로를 다시 계산. 출발 전 노선은 버튼으로만."""
    out = {"date": d.isoformat(), "managers": 0, "calls": 0, "fresh": 0}
    if not enabled():
        out["stopped"] = "ROUTE_LEGS_MODE 꺼짐"
        return out
    started, left = set(), set()
    for s in day_cache.get_day(d).get("stops") or []:
        if s.get("manager_id") is None or not s.get("has_coord"):
            continue
        (started if s.get("delivered_at") else left).add(int(s["manager_id"]))
    for mid in sorted(started & left):
        try:
            r = preview(d, mid, purpose="eta", every=ETA_EVERY)
        except StopCalls as e:
            out["stopped"] = str(e)
            break
        except Exception:  # noqa: BLE001
            logger.exception("route eta %s 계정 %s 실패 — 다음 주기에 다시", d, mid)
            continue
        out["managers"] += 1
        out["calls"] += int(r.get("calls") or 0)
        out["fresh"] += 1 if r.get("cached") else 0
    return out


def _control(d: date, mid: int, legs: list[dict], stops: list[dict], last: dict | None, rem_ids: list[str],
             now: datetime, skip: set | None = None) -> dict:
    """[S3-P2d-4b] 노선 관제: 배송지별 희망 시각 대비 예상 도착(남은 곳)·완료 시각(완료한 곳), 정체·대기 (NAVER 호출 없음)."""
    info: dict = {}
    target_of: dict = {}
    done_stops: list[dict] = []
    excluded: list[dict] = []    
    last_at = None
    for s in stops:
        if s.get("manager_id") is None or int(s["manager_id"]) != mid:
            continue
        sid = str(s.get("delivery_id") or s.get("address_id"))
        aid = int(s["address_id"]) if s.get("address_id") is not None else None
        info[sid] = {"name": s.get("address_name") or sid, "seq": s.get("seq"), "address_id": aid}
        if skip and aid in skip:          # [S3-P2d-5] 관제 제외 → 완료·지연·정체 판단에서 뺌 (지도에는 그대로)
            at_x = to_kst(s.get("delivered_at"))
            excluded.append({"id": sid, **info[sid], "target_at": None, "delay_min": None,
                             "done_at": at_x.isoformat() if at_x else None})
            continue
        tg = target_at(d, s.get("delivery_time"))
        target_of[sid] = tg
        at = to_kst(s.get("delivered_at"))
        if at:
            last_at = at if last_at is None or at > last_at else last_at
            done_stops.append({"id": sid, **info[sid], "target_at": tg.isoformat() if tg else None,
                               "done_at": at.isoformat(), "delay_min": delay_min(at, tg)})
    done_stops.sort(key=lambda x: x["done_at"])
    dw = dwell_ms([(to_kst(x["delivered_at"]), int(x["duration_ms"] or 0)) for x in legs if x.get("delivered_at")])
    c = control_summary((last or {}).get("groups") or [], rem_ids, last_at, dw, now, target_of, STALL_MIN,
                        d == now.date())
    for x in c["stops"]:
        x.update(info.get(x["id"], {"name": x["id"], "seq": None}))
    c["no_time"] = [info.get(i, {}).get("name", i) for i in c.pop("no_time_ids")]
    late_done = sum(1 for x in done_stops if (x["delay_min"] or 0) >= 1)
    return {**c, "done": len(done_stops), "late_done": late_done, "done_stops": done_stops, "excluded": excluded,
            "calc_at": (last or {}).get("calc_at")}


def preview_all_status(d: date) -> dict:
    return _jget(_all_key(d)) or {"status": "idle"}


def start_preview_all(d: date) -> dict:
    """전체 노선 미리보기: 뒤에서 계산(화면은 진행률 조회). 이미 도는 중이면 그 상태를 돌려줌 (10분 넘으면 새로 시작)."""
    st = _jget(_all_key(d))
    now_ts = datetime.now(KST).timestamp()
    if st and st.get("status") == "running" and float(st.get("started_ts") or 0) > now_ts - 600:
        return st
    stops = day_cache.get_day(d).get("stops") or []
    mids = sorted({int(s["manager_id"]) for s in stops
                   if s.get("manager_id") is not None and s.get("has_coord") and not s.get("delivered_at")})
    st = {"status": "running", "total": len(mids), "done": 0, "calls": 0, "failed": [], "started_ts": now_ts}
    _jset(_all_key(d), st)
    threading.Thread(target=_run_all, args=(d, mids, st), daemon=True).start()
    return st


def _run_all(d: date, mids: list[int], st: dict) -> None:
    lock = threading.Lock()

    def one(mid: int) -> None:
        try:
            r, err = preview(d, mid), None
        except Exception as e:  # noqa: BLE001
            r, err = None, str(e)
            if not isinstance(e, StopCalls):
                logger.exception("전체 미리보기 %s 계정 %s 실패", d, mid)
        with lock:
            st["done"] += 1
            if r:
                st["calls"] += int(r.get("calls") or 0)
            else:
                st["failed"].append({"manager_id": mid, "error": err})
            _jset(_all_key(d), st)

    with ThreadPoolExecutor(max_workers=PREVIEW_WORKERS) as ex:
        list(ex.map(one, mids))
    st["status"] = "done"
    _jset(_all_key(d), st)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for arg in sys.argv[1:]:
        r = collect(date.fromisoformat(arg), purpose="backfill")
        print(r)
        if r.get("stopped"):      # 한도 도달·호출 꺼짐 → 남은 날짜는 다음 실행에서
            break
