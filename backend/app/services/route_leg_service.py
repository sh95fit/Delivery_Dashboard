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
from datetime import date, datetime

import requests
from sqlalchemy import text

from app.database import get_dash_engine
from app.services import dash_db, day_cache, routes_service
from app.services.day_aggregate import KST, to_kst
from app.services.route_leg_calc import alloc, chunks, coord_key, pending_groups, split_legs

logger = logging.getLogger("route_legs")

D5_URL = "https://maps.apigw.ntruss.com/map-direction/v1/driving"
API = "d5"
DAILY_LIMIT = int(os.environ.get("ROUTE_DAILY_LIMIT", "1500"))
MONTHLY_LIMIT = int(os.environ.get("ROUTE_MONTHLY_LIMIT", "55000"))
BACKFILL_RESERVE = 500          # 지난 날짜 채우기는 하루 한도에서 500회를 남기고 멈춤 (당일 경로 우선)
UNREACHABLE = (2, 3, 4, 5)      # 도로와 너무 멂·자동차 길 없음 등 → 그 지점만 '연결 불가'

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
    limit = DAILY_LIMIT - (BACKFILL_RESERVE if purpose == "backfill" else 0)
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
    if r.status_code != 200:
        raise RuntimeError(f"NAVER HTTP {r.status_code}: {r.text[:200]}")
    j = r.json()
    code = int(j.get("code", -1))
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for arg in sys.argv[1:]:
        print(collect(date.fromisoformat(arg), purpose="backfill"))
