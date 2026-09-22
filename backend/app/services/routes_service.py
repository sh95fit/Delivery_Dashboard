"""Google Routes API 클라이언트 — 캐시 우선 + 비용 통제."""
import logging
import os
from datetime import date as date_type

import requests
from sqlalchemy import text

from app.database import get_dash_engine, get_engine

logger = logging.getLogger("routes")

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline"
ORIGIN = {"location": {"latLng": {
    "latitude": float(os.environ.get("DEPOT_LAT", "37.5665")),
    "longitude": float(os.environ.get("DEPOT_LNG", "126.9780")),
}}}


def _waypoints_for(target: date_type, manager_id: int) -> list[dict]:
    """매니저의 당일 배송지 좌표 시퀀스 (stops 순서 무시 — 입력 순서대로, 추후 최적화)."""
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT d.address_id, a.latitude, a.longitude
            FROM delivery d
            JOIN addresses a ON a.id = d.address_id
            WHERE d.date = :d AND d.deleted_at IS NULL AND d.manager_id = :m
        """), {"d": target, "m": manager_id}).fetchall()
    return [
        {"via": True, "location": {"latLng": {"latitude": float(r.latitude),
                                              "longitude": float(r.longitude)}}}
        for r in rows
    ]


def _cache_get(route_key: str) -> dict | None:
    with get_dash_engine().connect() as conn:
        row = conn.execute(text("""
            SELECT polyline, distance_m, duration_s, stops_count
            FROM route_cache WHERE route_key = :k
        """), {"k": route_key}).fetchone()
    if not row:
        return None
    return {"polyline": row.polyline, "distance_m": int(row.distance_m),
            "duration_s": int(row.duration_s), "stops_count": int(row.stops_count),
            "source": "cache"}


def _cache_put(route_key: str, data: dict) -> None:
    engine = get_dash_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO route_cache (route_key, polyline, distance_m, duration_s, stops_count)
            VALUES (:k, :p, :dm, :ds, :sc)
            ON CONFLICT (route_key) DO UPDATE SET
                polyline = EXCLUDED.polyline, distance_m = EXCLUDED.distance_m,
                duration_s = EXCLUDED.duration_s, stops_count = EXCLUDED.stops_count,
                created_at = NOW()
        """), {"k": route_key, "p": data["polyline"], "dm": data["distance_m"],
               "ds": data["duration_s"], "sc": data["stops_count"]})
        conn.commit()


def _routes_api(waypoints: list[dict]) -> dict:
    key = os.environ.get("GOOGLE_ROUTES_API_KEY", "")
    if not key or len(waypoints) < 2:
        raise ValueError("Routes API 키 없음 또는 경유지 부족")

    # 경유지 25개 초과 → 청크 분할 호출 (v7 Day 15 요구사항)
    chunks, out = [], {"polyline": "", "distance_m": 0, "duration_s": 0,
                       "stops_count": len(waypoints)}
    pts = [ORIGIN["location"]] + [w["location"] for w in waypoints] + [ORIGIN["location"]]
    step = 24
    for i in range(0, len(pts) - 1, step):
        seg = pts[i:i + step + 1]
        body = {
            "origin": {"location": seg[0]},
            "destination": {"location": seg[-1]},
            "intermediates": [{"location": p} for p in seg[1:-1]],
            "travelMode": "DRIVE",
            "polylineQuality": "HIGH_QUALITY",
        }
        resp = requests.post(
            ROUTES_URL, json=body,
            headers={"Content-Type": "application/json",
                     "X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELD_MASK},
            timeout=15,
        )
        resp.raise_for_status()
        route = resp.json()["routes"][0]
        out["polyline"] += route["polyline"]["encodedPolyline"]
        out["distance_m"] += int(route["distanceMeters"])
        out["duration_s"] += int(route["duration"].rstrip("s"))
    return out


def get_route(target: date_type, manager_id: int, force: bool = False) -> dict:
    """캐시 우선 → 미스 시 Routes API → 캐시 저장."""
    route_key = f"{manager_id}:{target.isoformat()}"
    if not force:
        cached = _cache_get(route_key)
        if cached:
            return cached
    try:
        waypoints = _waypoints_for(target, manager_id)
        data = _routes_api(waypoints)
        data["source"] = "routes_api"
        _cache_put(route_key, data)
        return data
    except Exception as exc:
        logger.warning("Routes API 실패 (%s) — 폴리라인 없이 폴백", exc)
        return {"polyline": "", "distance_m": 0, "duration_s": 0,
                "stops_count": 0, "source": "unavailable"}


def force_refresh(target: date_type, manager_id: int) -> dict:
    return get_route(target, manager_id, force=True)
