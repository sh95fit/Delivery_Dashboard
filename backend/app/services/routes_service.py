"""Google Routes API 클라이언트 — 기본 출발지 등록형 + cache 우선."""
from __future__ import annotations

import os
from datetime import date as date_type

import requests
from sqlalchemy import text

from app.database import get_dash_engine, get_engine

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline"


def _active_origin() -> tuple[dict, str]:
    """우선 DB의 활성 출발지, 없으면 .env fallback."""
    with get_dash_engine().connect() as conn:
        row = conn.execute(text("""
            SELECT id, name, latitude, longitude
            FROM route_origins
            WHERE is_active = TRUE
            ORDER BY id DESC
            LIMIT 1
        """)).fetchone()

    if row:
        origin = {
            "name": row.name,
            "latitude": float(row.latitude),
            "longitude": float(row.longitude),
        }
        origin_sig = f"db-{row.id}"
        return origin, origin_sig

    lat = os.environ.get("DEPOT_LAT")
    lng = os.environ.get("DEPOT_LNG")
    if lat and lng:
        origin = {
            "name": "ENV fallback",
            "latitude": float(lat),
            "longitude": float(lng),
        }
        origin_sig = f"env-{lat},{lng}"
        return origin, origin_sig

    raise RuntimeError("출발지(route_origins 또는 DEPOT_LAT/LNG)가 없습니다")


def _route_key(manager_id: int, target: date_type, origin_sig: str) -> str:
    return f"{manager_id}:{target.isoformat()}:{origin_sig}"


def _cache_get(route_key: str) -> dict | None:
    with get_dash_engine().connect() as conn:
        row = conn.execute(text("""
            SELECT polyline, distance_m, duration_s, stops_count, source
            FROM route_cache
            WHERE route_key = :k
        """), {"k": route_key}).fetchone()

    if not row:
        return None

    return {
        "polyline": row.polyline,
        "distance_m": int(row.distance_m),
        "duration_s": int(row.duration_s),
        "stops_count": int(row.stops_count),
        "source": "cache",
    }


def _cache_put(route_key: str, data: dict) -> None:
    engine = get_dash_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO route_cache (route_key, polyline, distance_m, duration_s, stops_count, source)
            VALUES (:k, :p, :dm, :ds, :sc, :src)
            ON CONFLICT (route_key)
            DO UPDATE SET
                polyline = EXCLUDED.polyline,
                distance_m = EXCLUDED.distance_m,
                duration_s = EXCLUDED.duration_s,
                stops_count = EXCLUDED.stops_count,
                source = EXCLUDED.source,
                created_at = NOW()
        """), {
            "k": route_key,
            "p": data["polyline"],
            "dm": data["distance_m"],
            "ds": data["duration_s"],
            "sc": data["stops_count"],
            "src": data.get("source", "routes_api"),
        })
        conn.commit()


def _decode_polyline(encoded: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    index = lat = lng = 0

    while index < len(encoded):
        shift = result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        delta_lat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += delta_lat

        shift = result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        delta_lng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += delta_lng

        points.append((lat / 1e5, lng / 1e5))

    return points


def _encode_polyline(points: list[tuple[float, float]]) -> str:
    def encode_value(value: int) -> str:
        value = ~(value << 1) if value < 0 else (value << 1)
        chunks = []
        while value >= 0x20:
            chunks.append(chr((0x20 | (value & 0x1F)) + 63))
            value >>= 5
        chunks.append(chr(value + 63))
        return "".join(chunks)

    result: list[str] = []
    prev_lat = prev_lng = 0

    for lat, lng in points:
        ilat = int(round(lat * 1e5))
        ilng = int(round(lng * 1e5))
        result.append(encode_value(ilat - prev_lat))
        result.append(encode_value(ilng - prev_lng))
        prev_lat = ilat
        prev_lng = ilng

    return "".join(result)


def _fetch_stop_points(target: date_type, manager_id: int) -> tuple[str, list[dict]]:
    """실제 delivery가 있으면 delivery 기준, 없으면 orders+addresses 기준."""
    engine = get_engine()
    with engine.connect() as conn:
        exists_row = conn.execute(text("""
            SELECT COUNT(*)
            FROM delivery
            WHERE date = :d
              AND deleted_at IS NULL
        """), {"d": target}).fetchone()
        has_delivery = int(exists_row[0] or 0) > 0

        if has_delivery:
            rows = conn.execute(text("""
                SELECT DISTINCT d.id AS item_id,
                       a.latitude,
                       a.longitude,
                       a.delivery_hour,
                       a.name,
                       a.detail_address
                FROM delivery d
                JOIN addresses a
                  ON a.id = d.address_id
                WHERE d.date = :d
                  AND d.deleted_at IS NULL
                  AND d.manager_id = :m
                  AND a.latitude IS NOT NULL
                  AND a.longitude IS NOT NULL
            """), {"d": target, "m": manager_id}).fetchall()
            mode = "delivery"
        else:
            rows = conn.execute(text("""
                SELECT DISTINCT a.id AS item_id,
                       a.latitude,
                       a.longitude,
                       a.delivery_hour,
                       a.name,
                       a.detail_address
                FROM orders o
                JOIN addresses a
                  ON a.id = o.address_id
                WHERE o.delivery_date = :d
                  AND o.deleted_at IS NULL
                  AND a.manager_id = :m
                  AND a.latitude IS NOT NULL
                  AND a.longitude IS NOT NULL
            """), {"d": target, "m": manager_id}).fetchall()
            mode = "orders_estimate"

    items = []
    for row in rows:
        items.append({
            "id": row.item_id,
            "latitude": float(row.latitude),
            "longitude": float(row.longitude),
            "delivery_hour": row.delivery_hour,
            "name": row.name,
            "detail_address": row.detail_address,
        })

    # 예상/실제 순서는 delivery_hour → 이름 → id 로 정렬 (현재 단계의 임시 표준)
    def sort_key(x: dict):
        raw = x.get("delivery_hour") or ""
        # delivery_service와 동일한 정규화 철학: 대표 시간 추출 시도
        import re
        m = re.search(r"(\d{1,2}):(\d{2})", raw)
        if m:
            t = f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
        else:
            m = re.search(r"(\d{1,2})시\s*(\d{1,2})분", raw)
            if m:
                t = f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
            else:
                m = re.search(r"(\d{1,2})시", raw)
                t = f"{int(m.group(1)):02d}:00" if m else "99:99"
        return (t, x.get("name") or "", x["id"])

    items.sort(key=sort_key)
    return mode, items


def _compute_segment(origin: dict, destination: dict, intermediates: list[dict]) -> dict:
    key = os.environ.get("GOOGLE_ROUTES_API_KEY", "")
    if not key:
        raise RuntimeError("GOOGLE_ROUTES_API_KEY가 없습니다")

    body = {
        "origin": {
            "location": {
                "latLng": {
                    "latitude": origin["latitude"],
                    "longitude": origin["longitude"],
                }
            }
        },
        "destination": {
            "location": {
                "latLng": {
                    "latitude": destination["latitude"],
                    "longitude": destination["longitude"],
                }
            }
        },
        "intermediates": [
            {
                "location": {
                    "latLng": {
                        "latitude": p["latitude"],
                        "longitude": p["longitude"],
                    }
                }
            }
            for p in intermediates
        ],
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_UNAWARE",
        "polylineQuality": "HIGH_QUALITY",
        "languageCode": "ko-KR",
        "units": "METRIC",
    }

    resp = requests.post(
        ROUTES_URL,
        json=body,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        timeout=20,
    )
    resp.raise_for_status()

    route = resp.json()["routes"][0]
    return {
        "polyline": route["polyline"]["encodedPolyline"],
        "distance_m": int(route["distanceMeters"]),
        "duration_s": int(route["duration"].rstrip("s")),
    }


def _compute_route(origin: dict, stops: list[dict]) -> dict:
    """경유지 25개 제한을 고려해 세그먼트 단위로 계산 후 하나의 polyline으로 합친다."""
    if len(stops) == 0:
        return {
            "polyline": "",
            "distance_m": 0,
            "duration_s": 0,
            "stops_count": 0,
            "source": "unavailable",
        }

    max_chunk = 24  # 안전하게 24개 stop씩
    segments: list[dict] = []
    current_origin = origin
    remaining = stops[:]

    while remaining:
        chunk = remaining[:max_chunk]
        remaining = remaining[max_chunk:]

        if remaining:
            destination = chunk[-1]
            intermediates = chunk[:-1]
        else:
            destination = origin
            intermediates = chunk

        segment = _compute_segment(current_origin, destination, intermediates)
        segments.append(segment)
        current_origin = destination

    all_points: list[tuple[float, float]] = []
    total_distance = 0
    total_duration = 0

    for i, seg in enumerate(segments):
        pts = _decode_polyline(seg["polyline"])
        if i > 0 and pts:
            pts = pts[1:]
        all_points.extend(pts)
        total_distance += seg["distance_m"]
        total_duration += seg["duration_s"]

    return {
        "polyline": _encode_polyline(all_points) if all_points else "",
        "distance_m": total_distance,
        "duration_s": total_duration,
        "stops_count": len(stops),
        "source": "routes_api",
    }


def get_route(target: date_type, manager_id: int, force: bool = False) -> dict:
    origin, origin_sig = _active_origin()
    route_key = _route_key(manager_id, target, origin_sig)

    mode, stops = _fetch_stop_points(target, manager_id)
    if not stops:
        return {
            "polyline": "",
            "distance_m": 0,
            "duration_s": 0,
            "stops_count": 0,
            "source": "unavailable",
            "mode": mode,
            "origin_name": origin["name"],
        }

    if not force:
        cached = _cache_get(route_key)
        if cached:
            cached["mode"] = mode
            cached["origin_name"] = origin["name"]
            return cached

    try:
        data = _compute_route(origin, stops)
        _cache_put(route_key, data)
        data["mode"] = mode
        data["origin_name"] = origin["name"]
        return data
    except Exception:
        return {
            "polyline": "",
            "distance_m": 0,
            "duration_s": 0,
            "stops_count": len(stops),
            "source": "unavailable",
            "mode": mode,
            "origin_name": origin["name"],
        }


def force_refresh(target: date_type, manager_id: int) -> dict:
    return get_route(target, manager_id, force=True)
