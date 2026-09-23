"""차량 경로 계산 서비스.
- 기본 상태: 전체 차량 노선 반환
- RESULT: 실제 완료 경로(delivered_at ASC)
- LIVE: 완료 구간 + 남은 구간 분리
- PREVIEW: 출발지 기준 가까운 거리 우선(Nearest Neighbor) 예상 경로
- 출발지: route_origins 우선, 없으면 ENV fallback
- Google Routes API waypoint 제한 대응: 20개 단위 배치
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import date as date_type

import requests
from sqlalchemy import text

from app.database import get_dash_engine, get_engine

ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline,fallbackInfo"
MAX_STOPS_PER_BATCH = 20


def _normalize_delivery_hour(raw: str | None) -> str:
    if not raw:
        return "99:99"
    text_value = raw.strip()
    if not text_value:
        return "99:99"

    m = re.search(r"(\d{1,2}):(\d{2})", text_value)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return f"{hh:02d}:{mm:02d}"

    m = re.search(r"(\d{1,2})시\s*(\d{1,2})분", text_value)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return f"{hh:02d}:{mm:02d}"

    m = re.search(r"(\d{1,2})시", text_value)
    if m:
        hh = int(m.group(1))
        if 0 <= hh <= 23:
            return f"{hh:02d}:00"

    return "99:99"


def _active_origin() -> tuple[dict, str]:
    """DB의 활성 출발지 우선, 없으면 ENV fallback."""
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


def _cache_key(target: date_type, manager_id: int, state: str, origin_sig: str, stop_signature: str) -> str:
    return f"{target.isoformat()}:{manager_id}:{state}:{origin_sig}:{stop_signature}"


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

    if not resp.ok:
        raise RuntimeError(f"Routes API HTTP {resp.status_code}: {resp.text}")

    try:
        payload = resp.json()
    except Exception as exc:
        raise RuntimeError(f"Routes API JSON 파싱 실패: {resp.text}") from exc

    routes = payload.get("routes")

    # 핵심: routes가 없거나 비어 있으면 '경로 없음'으로 처리
    if not routes:
        return {
            "polyline": "",
            "distance_m": 0,
            "duration_s": 0,
            "source": "unavailable",
            "raw_response": payload,
        }

    route = routes[0]

    polyline = route.get("polyline", {}).get("encodedPolyline")
    distance_m = route.get("distanceMeters")
    duration_raw = route.get("duration")

    if not polyline or distance_m is None or not duration_raw:
        return {
            "polyline": "",
            "distance_m": 0,
            "duration_s": 0,
            "source": "unavailable",
            "raw_response": payload,
        }

    return {
        "polyline": polyline,
        "distance_m": int(distance_m),
        "duration_s": int(str(duration_raw).rstrip("s")),
        "source": "routes_api",
        "raw_response": payload,
    }


def _compute_route_batched(origin: dict, ordered_stops: list[dict]) -> dict:
    """20개 단위 배치 처리. 직전 마지막 도착지를 다음 배치 출발지로 사용."""
    if len(ordered_stops) == 0:
        return {
            "polyline": "",
            "distance_m": 0,
            "duration_s": 0,
            "stops_count": 0,
            "source": "unavailable",
            "raw_responses": [],
        }

    segments: list[dict] = []
    current_origin = origin
    remaining = ordered_stops[:]

    while remaining:
        chunk = remaining[:MAX_STOPS_PER_BATCH]
        remaining = remaining[MAX_STOPS_PER_BATCH:]

        destination = chunk[-1]
        intermediates = chunk[:-1]

        segment = _compute_segment(current_origin, destination, intermediates)
        segments.append(segment)
        current_origin = destination

    all_points: list[tuple[float, float]] = []
    total_distance = 0
    total_duration = 0
    raw_responses: list[dict] = []
    success_count = 0

    for i, seg in enumerate(segments):
        if seg.get("raw_response") is not None:
            raw_responses.append(seg["raw_response"])

        if not seg["polyline"]:
            continue

        pts = _decode_polyline(seg["polyline"])
        if i > 0 and pts:
            pts = pts[1:]
        all_points.extend(pts)
        total_distance += seg["distance_m"]
        total_duration += seg["duration_s"]
        success_count += 1

    if success_count == 0:
        return {
            "polyline": "",
            "distance_m": 0,
            "duration_s": 0,
            "stops_count": len(ordered_stops),
            "source": "unavailable",
            "raw_responses": raw_responses,
        }

    return {
        "polyline": _encode_polyline(all_points) if all_points else "",
        "distance_m": total_distance,
        "duration_s": total_duration,
        "stops_count": len(ordered_stops),
        "source": "routes_api",
        "raw_responses": raw_responses,
    }


def _fetch_state_and_groups(target: date_type) -> tuple[str, str, list[dict]]:
    """state, source, manager 그룹별 stop 원천데이터 반환."""
    engine = get_engine()
    with engine.connect() as conn:
        status_row = conn.execute(text("""
            SELECT COUNT(*) AS delivery_count,
                   COUNT(CASE WHEN delivered_at IS NOT NULL THEN 1 END) AS delivered_count
            FROM delivery
            WHERE date = :d
              AND deleted_at IS NULL
        """), {"d": target}).fetchone()

        delivery_count = int(status_row[0] or 0)
        delivered_count = int(status_row[1] or 0)

        if delivery_count == 0:
            state = "PREVIEW"
            source = "orders_estimate"
        elif delivered_count >= delivery_count:
            state = "RESULT"
            source = "delivery"
        else:
            state = "LIVE"
            source = "delivery"

        if source == "delivery":
            rows = conn.execute(text("""
                SELECT d.id AS item_id,
                       d.manager_id,
                       m.name AS manager_name,
                       m.color AS manager_color,
                       a.latitude,
                       a.longitude,
                       a.delivery_hour,
                       a.name AS address_name,
                       a.detail_address,
                       d.delivered_at
                FROM delivery d
                JOIN addresses a ON a.id = d.address_id
                LEFT JOIN manager m ON m.id = d.manager_id
                WHERE d.date = :d
                  AND d.deleted_at IS NULL
                  AND a.latitude IS NOT NULL
                  AND a.longitude IS NOT NULL
            """), {"d": target}).fetchall()
        else:
            rows = conn.execute(text("""
                SELECT DISTINCT a.id AS item_id,
                       a.manager_id,
                       m.name AS manager_name,
                       m.color AS manager_color,
                       a.latitude,
                       a.longitude,
                       a.delivery_hour,
                       a.name AS address_name,
                       a.detail_address,
                       NULL AS delivered_at
                FROM orders o
                JOIN addresses a ON a.id = o.address_id
                LEFT JOIN manager m ON m.id = a.manager_id
                WHERE o.delivery_date = :d
                  AND o.deleted_at IS NULL
                  AND a.latitude IS NOT NULL
                  AND a.longitude IS NOT NULL
            """), {"d": target}).fetchall()

    items = []
    for r in rows:
        items.append({
            "id": r.item_id,
            "manager_id": r.manager_id,
            "manager_name": r.manager_name,
            "manager_color": r.manager_color,
            "latitude": float(r.latitude),
            "longitude": float(r.longitude),
            "delivery_hour": r.delivery_hour,
            "delivery_time": _normalize_delivery_hour(r.delivery_hour),
            "address_name": r.address_name,
            "detail_address": r.detail_address,
            "delivered_at": r.delivered_at,
        })

    return state, source, items


def _distance_sq(origin: dict, stop: dict) -> float:
    return (origin["latitude"] - stop["latitude"]) ** 2 + (origin["longitude"] - stop["longitude"]) ** 2


def _preview_nearest_neighbor(origin: dict, stops: list[dict]) -> list[dict]:
    remaining = stops[:]
    ordered: list[dict] = []
    current = {"latitude": origin["latitude"], "longitude": origin["longitude"]}

    while remaining:
        nxt = min(
            remaining,
            key=lambda s: (_distance_sq(current, s), s["delivery_time"], s["address_name"] or "", s["id"]),
        )
        ordered.append(nxt)
        remaining.remove(nxt)
        current = {"latitude": nxt["latitude"], "longitude": nxt["longitude"]}

    return ordered


def _build_manager_route(target: date_type, state: str, source: str, origin: dict, origin_sig: str,
                         manager_id: int, manager_name: str | None, manager_color: str | None,
                         manager_stops: list[dict], force: bool = False) -> dict:
    if state == "RESULT":
        completed = sorted(
            [s for s in manager_stops if s["delivered_at"] is not None],
            key=lambda s: (s["delivered_at"], s["id"]),
        )
        remaining: list[dict] = []
    elif state == "LIVE":
        completed = sorted(
            [s for s in manager_stops if s["delivered_at"] is not None],
            key=lambda s: (s["delivered_at"], s["id"]),
        )
        remaining = sorted(
            [s for s in manager_stops if s["delivered_at"] is None],
            key=lambda s: (s["delivery_time"], s["address_name"] or "", s["id"]),
        )
    else:  # PREVIEW
        completed = []
        remaining = _preview_nearest_neighbor(origin, manager_stops)

    stop_signature_src = [
        f"{s['id']}:{s['latitude']},{s['longitude']}:{s['delivery_time']}:{s['delivered_at']}"
        for s in completed + remaining
    ]
    stop_signature = hashlib.sha1("|".join(stop_signature_src).encode()).hexdigest()[:12]
    route_key = _cache_key(target, manager_id, state, origin_sig, stop_signature)

    if not force:
        cached = _cache_get(route_key)
        if cached:
            return {
                "manager_id": manager_id,
                "manager_name": manager_name,
                "manager_color": manager_color,
                "mode": state.lower(),
                "completed_polyline": cached["polyline"] if state == "RESULT" else (cached["polyline"] if not remaining else ""),
                "remaining_polyline": "" if state == "RESULT" else (cached["polyline"] if not completed else ""),
                "distance_m": cached["distance_m"],
                "duration_s": cached["duration_s"],
                "completed_stops": len(completed),
                "remaining_stops": len(remaining),
                "origin_name": origin["name"],
                "source": "cache",
            }

    completed_route = {
        "polyline": "",
        "distance_m": 0,
        "duration_s": 0,
        "stops_count": 0,
        "source": "unavailable",
    }
    remaining_route = {
        "polyline": "",
        "distance_m": 0,
        "duration_s": 0,
        "stops_count": 0,
        "source": "unavailable",
    }

    if completed:
        completed_route = _compute_route_batched(origin, completed)

    if remaining:
        # 남은 구간은 마지막 완료지(있으면)부터 시작, 없으면 origin부터 시작
        rem_origin = origin
        if completed:
            last = completed[-1]
            rem_origin = {
                "name": "last_completed",
                "latitude": last["latitude"],
                "longitude": last["longitude"],
            }
        remaining_route = _compute_route_batched(rem_origin, remaining)

    distance_m = completed_route["distance_m"] + remaining_route["distance_m"]
    duration_s = completed_route["duration_s"] + remaining_route["duration_s"]

    overall_source = (
        "unavailable"
        if completed_route["source"] == "unavailable" and remaining_route["source"] == "unavailable"
        else "routes_api"
    )

    cache_payload = {
        "polyline": completed_route["polyline"] or remaining_route["polyline"],
        "distance_m": distance_m,
        "duration_s": duration_s,
        "stops_count": len(completed) + len(remaining),
        "source": overall_source,
    }

    # 빈 경로는 cache 저장하지 않음
    if cache_payload["polyline"]:
        _cache_put(route_key, cache_payload)

    return {
        "manager_id": manager_id,
        "manager_name": manager_name,
        "manager_color": manager_color,
        "mode": state.lower(),
        "completed_polyline": completed_route["polyline"],
        "remaining_polyline": remaining_route["polyline"],
        "distance_m": distance_m,
        "duration_s": duration_s,
        "completed_stops": len(completed),
        "remaining_stops": len(remaining),
        "origin_name": origin["name"],
        "source": overall_source,
        "raw_responses": {
            "completed": completed_route.get("raw_responses", []),
            "remaining": remaining_route.get("raw_responses", []),
        },
    }



def get_routes(target: date_type, force: bool = False) -> dict:
    origin, origin_sig = _active_origin()
    state, source, items = _fetch_state_and_groups(target)

    groups: dict[int, dict] = {}
    for item in items:
        if item["manager_id"] is None:
            continue
        groups.setdefault(item["manager_id"], {
            "manager_name": item["manager_name"],
            "manager_color": item["manager_color"],
            "items": [],
        })["items"].append(item)

    routes = []
    for manager_id, payload in groups.items():
        routes.append(
            _build_manager_route(
                target=target,
                state=state,
                source=source,
                origin=origin,
                origin_sig=origin_sig,
                manager_id=manager_id,
                manager_name=payload["manager_name"],
                manager_color=payload["manager_color"],
                manager_stops=payload["items"],
                force=force,
            )
        )

    return {
        "date": target.isoformat(),
        "state": state,
        "source": source,
        "routes": routes,
    }


def get_route(target: date_type, manager_id: int, force: bool = False) -> dict:
    all_routes = get_routes(target, force=force)
    for route in all_routes["routes"]:
        if int(route["manager_id"]) == int(manager_id):
            return route
    return {
        "manager_id": manager_id,
        "manager_name": None,
        "manager_color": None,
        "mode": all_routes["state"].lower(),
        "completed_polyline": "",
        "remaining_polyline": "",
        "distance_m": 0,
        "duration_s": 0,
        "completed_stops": 0,
        "remaining_stops": 0,
        "origin_name": None,
        "source": "unavailable",
    }


def force_refresh(target: date_type, manager_id: int) -> dict:
    return get_route(target, manager_id, force=True)
