from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date as date_type, datetime, timedelta, timezone

import requests
from sqlalchemy import text

from app.database import get_dash_engine, get_engine

KST = timezone(timedelta(hours=9))
NAVER_DIRECTIONS_URL = "https://maps.apigw.ntruss.com/map-direction-15/v1/driving"
MAX_STOPS_PER_BATCH = 5


def _today_kst() -> date_type:
    return datetime.now(KST).date()


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
    with get_dash_engine().connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, name, latitude, longitude
                FROM route_origins
                WHERE is_active = TRUE
                ORDER BY id DESC
                LIMIT 1
                """
            )
        ).fetchone()

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


def _latest_opinet_fuel_price() -> int | None:
    try:
        with get_dash_engine().connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT price
                    FROM fuel_price_log
                    WHERE fuel_type = 'gasoline'
                    ORDER BY price_date DESC, id DESC
                    LIMIT 1
                    """
                )
            ).fetchone()
        return int(row.price) if row else None
    except Exception:
        return None


def _cache_key(target: date_type, manager_id: int, state: str, origin_sig: str, stop_signature: str) -> str:
    return f"{target.isoformat()}:{manager_id}:{state}:{origin_sig}:{stop_signature}"


def _cache_get(route_key: str) -> dict | None:
    with get_dash_engine().connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT route_key, state, completed_path_json, remaining_path_json,
                       distance_m, duration_s, completed_stops, remaining_stops,
                       toll_fare, fuel_price_naver, fuel_price_opinet,
                       origin_name, source, payload
                FROM route_cache
                WHERE route_key = :k
                """
            ),
            {"k": route_key},
        ).fetchone()

    if not row:
        return None

    return {
        "route_key": row.route_key,
        "state": row.state,
        "completed_path": row.completed_path_json or [],
        "remaining_path": row.remaining_path_json or [],
        "distance_m": int(row.distance_m or 0),
        "duration_ms": int(row.duration_s or 0),
        "completed_stops": int(row.completed_stops or 0),
        "remaining_stops": int(row.remaining_stops or 0),
        "toll_fare": int(row.toll_fare or 0),
        "fuel_price_naver": int(row.fuel_price_naver or 0),
        "fuel_price_opinet": row.fuel_price_opinet,
        "origin_name": row.origin_name,
        "source": "cache",
        "payload": row.payload or {},
    }


def _cache_put(route_key: str, state: str, stop_signature: str, payload: dict) -> None:
    engine = get_dash_engine()
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO route_cache (
                    route_key, state, polyline, distance_m, duration_s, stops_count, source,
                    completed_path_json, remaining_path_json, completed_stops, remaining_stops,
                    toll_fare, fuel_price_naver, fuel_price_opinet, origin_name, stop_signature, payload
                ) VALUES (
                    :route_key, :state, '', :distance_m, :duration_ms, :stops_count, :source,
                    CAST(:completed_path_json AS jsonb), CAST(:remaining_path_json AS jsonb),
                    :completed_stops, :remaining_stops,
                    :toll_fare, :fuel_price_naver, :fuel_price_opinet,
                    :origin_name, :stop_signature, CAST(:payload AS jsonb)
                )
                ON CONFLICT (route_key)
                DO UPDATE SET
                    state = EXCLUDED.state,
                    distance_m = EXCLUDED.distance_m,
                    duration_s = EXCLUDED.duration_s,
                    stops_count = EXCLUDED.stops_count,
                    source = EXCLUDED.source,
                    completed_path_json = EXCLUDED.completed_path_json,
                    remaining_path_json = EXCLUDED.remaining_path_json,
                    completed_stops = EXCLUDED.completed_stops,
                    remaining_stops = EXCLUDED.remaining_stops,
                    toll_fare = EXCLUDED.toll_fare,
                    fuel_price_naver = EXCLUDED.fuel_price_naver,
                    fuel_price_opinet = EXCLUDED.fuel_price_opinet,
                    origin_name = EXCLUDED.origin_name,
                    stop_signature = EXCLUDED.stop_signature,
                    payload = EXCLUDED.payload,
                    created_at = NOW()
                """
            ),
            {
                "route_key": route_key,
                "state": state,
                "distance_m": payload["distance_m"],
                "duration_ms": payload["duration_ms"],
                "stops_count": payload["completed_stops"] + payload["remaining_stops"],
                "source": payload["source"],
                "completed_path_json": json.dumps(payload["completed_path"]),
                "remaining_path_json": json.dumps(payload["remaining_path"]),
                "completed_stops": payload["completed_stops"],
                "remaining_stops": payload["remaining_stops"],
                "toll_fare": payload["toll_fare"],
                "fuel_price_naver": payload["fuel_price_naver"],
                "fuel_price_opinet": payload["fuel_price_opinet"],
                "origin_name": payload["origin_name"],
                "stop_signature": stop_signature,
                "payload": json.dumps(payload.get("payload", {})),
            },
        )
        conn.commit()


def _snapshot_insert(route_date: date_type, manager_id: int, state: str, trigger_reason: str, payload: dict) -> None:
    engine = get_dash_engine()
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO route_snapshots (
                    route_date, manager_id, state, trigger_reason, origin_name,
                    completed_stop_ids_json, remaining_stop_ids_json,
                    completed_path_json, remaining_path_json,
                    distance_m, duration_ms, toll_fare,
                    fuel_price_naver, fuel_price_opinet, payload
                ) VALUES (
                    :route_date, :manager_id, :state, :trigger_reason, :origin_name,
                    CAST(:completed_stop_ids_json AS jsonb), CAST(:remaining_stop_ids_json AS jsonb),
                    CAST(:completed_path_json AS jsonb), CAST(:remaining_path_json AS jsonb),
                    :distance_m, :duration_ms, :toll_fare,
                    :fuel_price_naver, :fuel_price_opinet, CAST(:payload AS jsonb)
                )
                """
            ),
            {
                "route_date": route_date,
                "manager_id": manager_id,
                "state": state,
                "trigger_reason": trigger_reason,
                "origin_name": payload["origin_name"],
                "completed_stop_ids_json": json.dumps(payload["completed_stop_ids"]),
                "remaining_stop_ids_json": json.dumps(payload["remaining_stop_ids"]),
                "completed_path_json": json.dumps(payload["completed_path"]),
                "remaining_path_json": json.dumps(payload["remaining_path"]),
                "distance_m": payload["distance_m"],
                "duration_ms": payload["duration_ms"],
                "toll_fare": payload["toll_fare"],
                "fuel_price_naver": payload["fuel_price_naver"],
                "fuel_price_opinet": payload["fuel_price_opinet"],
                "payload": json.dumps(payload.get("payload", {})),
            },
        )
        conn.commit()


def _job_state_get(route_date: date_type, manager_id: int, state: str) -> dict | None:
    with get_dash_engine().connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT current_signature, current_route_key, status, retry_count, next_retry_at
                FROM route_job_state
                WHERE route_date = :d AND manager_id = :m AND state = :s
                """
            ),
            {"d": route_date, "m": manager_id, "s": state},
        ).fetchone()
    if not row:
        return None
    return {
        "current_signature": row.current_signature,
        "current_route_key": row.current_route_key,
        "status": row.status,
        "retry_count": row.retry_count,
        "next_retry_at": row.next_retry_at,
    }


def _job_state_upsert(
    route_date: date_type,
    manager_id: int,
    state: str,
    signature: str,
    route_key: str,
    status: str,
    last_error: str | None = None,
    last_error_payload: dict | None = None,
    next_retry_at=None,
    retry_count: int = 0,
) -> None:
    engine = get_dash_engine()
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                INSERT INTO route_job_state (
                    route_date, manager_id, state, current_signature, current_route_key,
                    status, retry_count, next_retry_at, last_error, last_error_payload,
                    last_changed_at, last_collected_at
                ) VALUES (
                    :d, :m, :s, :sig, :rk,
                    :status, :retry_count, :next_retry_at, :last_error, CAST(:last_error_payload AS jsonb),
                    NOW(), NOW()
                )
                ON CONFLICT (route_date, manager_id, state)
                DO UPDATE SET
                    current_signature = EXCLUDED.current_signature,
                    current_route_key = EXCLUDED.current_route_key,
                    status = EXCLUDED.status,
                    retry_count = EXCLUDED.retry_count,
                    next_retry_at = EXCLUDED.next_retry_at,
                    last_error = EXCLUDED.last_error,
                    last_error_payload = EXCLUDED.last_error_payload,
                    last_changed_at = NOW(),
                    last_collected_at = NOW()
                """
            ),
            {
                "d": route_date,
                "m": manager_id,
                "s": state,
                "sig": signature,
                "rk": route_key,
                "status": status,
                "retry_count": retry_count,
                "next_retry_at": next_retry_at,
                "last_error": last_error,
                "last_error_payload": json.dumps(last_error_payload or {}),
            },
        )
        conn.commit()


def _job_state_touch(route_date: date_type, manager_id: int, state: str) -> None:
    engine = get_dash_engine()
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                UPDATE route_job_state
                   SET last_collected_at = NOW()
                 WHERE route_date = :d AND manager_id = :m AND state = :s
                """
            ),
            {"d": route_date, "m": manager_id, "s": state},
        )
        conn.commit()


def _distance_sq(origin: dict, stop: dict) -> float:
    return (origin["latitude"] - stop["latitude"]) ** 2 + (origin["longitude"] - stop["longitude"]) ** 2


def _same_point(a: dict, b: dict, precision: int = 6) -> bool:
    return (
        round(float(a["latitude"]), precision) == round(float(b["latitude"]), precision)
        and round(float(a["longitude"]), precision) == round(float(b["longitude"]), precision)
    )


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


def _naver_headers() -> dict:
    key_id = os.environ.get("NAVER_MAPS_API_KEY_ID", "")
    key = os.environ.get("NAVER_MAPS_API_KEY", "")
    if not key_id or not key:
        raise RuntimeError("NAVER_MAPS_API_KEY_ID / NAVER_MAPS_API_KEY가 없습니다")
    return {
        "x-ncp-apigw-api-key-id": key_id,
        "x-ncp-apigw-api-key": key,
    }


def _to_lonlat(stop: dict) -> str:
    return f"{stop['longitude']},{stop['latitude']}"


def _group_route_nodes(stops: list[dict], precision: int = 6) -> list[dict]:
    """stop은 유지하고, 경로 계산용 좌표 node만 통합한다."""
    nodes: list[dict] = []
    index_by_key: dict[tuple[float, float], int] = {}

    for stop in stops:
        key = (
            round(float(stop["longitude"]), precision),
            round(float(stop["latitude"]), precision),
        )

        if key not in index_by_key:
            index_by_key[key] = len(nodes)
            nodes.append({
                "longitude": float(stop["longitude"]),
                "latitude": float(stop["latitude"]),
                "stop_ids": [stop["id"]],
                "stops": [stop],
            })
        else:
            idx = index_by_key[key]
            nodes[idx]["stop_ids"].append(stop["id"])
            nodes[idx]["stops"].append(stop)

    return nodes


def _build_node_signature(nodes: list[dict]) -> str:
    src = [
        f"{round(n['latitude'],6)},{round(n['longitude'],6)}:{','.join(map(str, n['stop_ids']))}"
        for n in nodes
    ]
    return hashlib.sha1("|".join(src).encode()).hexdigest()[:16]


def _naver_driving(start: dict, ordered_nodes: list[dict], option: str = "trafast") -> dict:
    if not ordered_nodes:
        return {
            "path": [],
            "distance_m": 0,
            "duration_ms": 0,
            "toll_fare": 0,
            "fuel_price_naver": 0,
            "payload": {},
            "source": "unavailable",
            "code": -1,
        }

    if len(ordered_nodes) == 1 and _same_point(start, ordered_nodes[0]):
        return {
            "path": [],
            "distance_m": 0,
            "duration_ms": 0,
            "toll_fare": 0,
            "fuel_price_naver": 0,
            "payload": {"note": "start and goal are same"},
            "source": "same_point",
            "code": 1,
        }

    params = {
        "start": f"{start['longitude']},{start['latitude']}",
        "goal": _to_lonlat(ordered_nodes[-1]),
        "option": option,
        "lang": "ko",
    }

    waypoints = ordered_nodes[:-1]
    if waypoints:
        params["waypoints"] = "|".join(_to_lonlat(x) for x in waypoints)

    resp = requests.get(
        NAVER_DIRECTIONS_URL,
        headers=_naver_headers(),
        params=params,
        timeout=20,
    )

    if not resp.ok:
        raise RuntimeError(f"NAVER Directions HTTP {resp.status_code}: {resp.text}")

    payload = resp.json()
    code = int(payload.get("code", -1))
    if code != 0:
        return {
            "path": [],
            "distance_m": 0,
            "duration_ms": 0,
            "toll_fare": 0,
            "fuel_price_naver": 0,
            "payload": payload,
            "source": "unavailable",
            "code": code,
        }

    route_obj = (payload.get("route") or {}).get(option)
    if not route_obj:
        return {
            "path": [],
            "distance_m": 0,
            "duration_ms": 0,
            "toll_fare": 0,
            "fuel_price_naver": 0,
            "payload": payload,
            "source": "unavailable",
            "code": -2,
        }

    route = route_obj[0]
    summary = route.get("summary", {})
    raw_path = route.get("path", [])
    path = [{"lat": float(lat), "lng": float(lng)} for lng, lat in raw_path]

    return {
        "path": path,
        "distance_m": int(summary.get("distance", 0) or 0),
        "duration_ms": int(summary.get("duration", 0) or 0),
        "toll_fare": int(summary.get("tollFare", 0) or 0),
        "fuel_price_naver": int(summary.get("fuelPrice", 0) or 0),
        "payload": payload,
        "source": "naver",
        "code": 0,
    }


def _merge_paths(chunks: list[list[dict]]) -> list[dict]:
    merged: list[dict] = []
    for i, chunk in enumerate(chunks):
        if i > 0 and chunk:
            chunk = chunk[1:]
        merged.extend(chunk)
    return merged


def _compute_route_batched(origin: dict, ordered_stops: list[dict]) -> dict:
    route_nodes = _group_route_nodes(ordered_stops)

    if len(route_nodes) == 0:
        return {
            "path": [],
            "distance_m": 0,
            "duration_ms": 0,
            "toll_fare": 0,
            "fuel_price_naver": 0,
            "source": "unavailable",
            "payloads": [],
            "status": "not_needed",
            "last_error": None,
            "last_error_payload": {},
        }

    chunks: list[dict] = []
    current_origin = origin
    remaining = route_nodes[:]

    while remaining:
        batch = remaining[:MAX_STOPS_PER_BATCH]
        remaining = remaining[MAX_STOPS_PER_BATCH:]

        while batch and _same_point(current_origin, batch[0]):
            batch = batch[1:]

        if not batch:
            continue

        result = _naver_driving(current_origin, batch)
        chunks.append(result)
        current_origin = batch[-1]

    good_chunks = [c for c in chunks if c["source"] in ("naver", "same_point")]
    nav_chunks = [c for c in chunks if c["source"] == "naver"]

    if not good_chunks:
        errors = [c for c in chunks if c["source"] == "unavailable"]
        retryable = any(c.get("code") in (-1,) for c in errors)
        status = "failed_retryable" if retryable else "failed_final"
        return {
            "path": [],
            "distance_m": 0,
            "duration_ms": 0,
            "toll_fare": 0,
            "fuel_price_naver": 0,
            "source": "unavailable",
            "payloads": [c.get("payload", {}) for c in chunks],
            "status": status,
            "last_error": "Naver directions unavailable",
            "last_error_payload": {"chunks": [c.get("payload", {}) for c in chunks]},
        }

    path = _merge_paths([c["path"] for c in nav_chunks]) if nav_chunks else []

    return {
        "path": path,
        "distance_m": sum(c["distance_m"] for c in nav_chunks),
        "duration_ms": sum(c["duration_ms"] for c in nav_chunks),
        "toll_fare": sum(c["toll_fare"] for c in nav_chunks),
        "fuel_price_naver": sum(c["fuel_price_naver"] for c in nav_chunks),
        "source": "naver" if nav_chunks else "same_point",
        "payloads": [c.get("payload", {}) for c in chunks],
        "status": "ready",
        "last_error": None,
        "last_error_payload": {},
    }


def _fetch_state_and_groups(target: date_type) -> tuple[str, str, list[dict]]:
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


def _build_stop_signature(stops: list[dict]) -> str:
    src = [
        f"{s['id']}:{s['latitude']},{s['longitude']}:{s['delivery_time']}:{s['delivered_at']}"
        for s in stops
    ]
    return hashlib.sha1("|".join(src).encode()).hexdigest()[:16]


def _next_retry_time(retry_count: int):
    now = datetime.now(KST)
    if retry_count <= 0:
        return now + timedelta(minutes=5)
    if retry_count == 1:
        return now + timedelta(minutes=15)
    return now + timedelta(hours=1)


def _build_manager_route(
    target: date_type,
    state: str,
    origin: dict,
    origin_sig: str,
    manager_id: int,
    manager_name: str | None,
    manager_color: str | None,
    manager_stops: list[dict],
    force: bool = False,
    trigger_reason: str = "api_read",
) -> dict:
    if not manager_stops:
        return {
            "manager_id": manager_id,
            "manager_name": manager_name,
            "manager_color": manager_color,
            "mode": state.lower(),
            "completed_path": [],
            "remaining_path": [],
            "distance_m": 0,
            "duration_ms": 0,
            "completed_stops": 0,
            "remaining_stops": 0,
            "toll_fare": 0,
            "fuel_price_naver": 0,
            "fuel_price_opinet": None,
            "origin_name": origin["name"],
            "source": "unavailable",
            "completed_stop_ids": [],
            "remaining_stop_ids": [],
            "payload": {},
            "status": "not_needed",
        }

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
    else:
        completed = []
        remaining = _preview_nearest_neighbor(origin, manager_stops)

    stop_signature = _build_node_signature(_group_route_nodes(completed + remaining))
    route_key = _cache_key(target, manager_id, state, origin_sig, stop_signature)

    if state == "RESULT" and not force:
        cached = _cache_get(route_key)
        if cached:
            return {
                "manager_id": manager_id,
                "manager_name": manager_name,
                "manager_color": manager_color,
                "mode": state.lower(),
                "completed_path": cached["completed_path"],
                "remaining_path": cached["remaining_path"],
                "distance_m": cached["distance_m"],
                "duration_ms": cached["duration_ms"],
                "completed_stops": cached["completed_stops"],
                "remaining_stops": cached["remaining_stops"],
                "toll_fare": cached["toll_fare"],
                "fuel_price_naver": cached["fuel_price_naver"],
                "fuel_price_opinet": cached["fuel_price_opinet"],
                "origin_name": cached["origin_name"],
                "source": "cache",
                "completed_stop_ids": [],
                "remaining_stop_ids": [],
                "payload": cached.get("payload", {}),
                "status": "ready",
            }

    if state == "LIVE" and not force:
        job = _job_state_get(target, manager_id, state)
        if (
            job
            and job["current_signature"] == stop_signature
            and job["current_route_key"] == route_key
            and job["status"] == "ready"
        ):
            cached = _cache_get(route_key)
            if cached:
                _job_state_touch(target, manager_id, state)
                return {
                    "manager_id": manager_id,
                    "manager_name": manager_name,
                    "manager_color": manager_color,
                    "mode": state.lower(),
                    "completed_path": cached["completed_path"],
                    "remaining_path": cached["remaining_path"],
                    "distance_m": cached["distance_m"],
                    "duration_ms": cached["duration_ms"],
                    "completed_stops": cached["completed_stops"],
                    "remaining_stops": cached["remaining_stops"],
                    "toll_fare": cached["toll_fare"],
                    "fuel_price_naver": cached["fuel_price_naver"],
                    "fuel_price_opinet": cached["fuel_price_opinet"],
                    "origin_name": cached["origin_name"],
                    "source": "cache",
                    "completed_stop_ids": [],
                    "remaining_stop_ids": [],
                    "payload": cached.get("payload", {}),
                    "status": "ready",
                }
        if job and job.get("status") == "failed_retryable" and job.get("next_retry_at"):
            if datetime.now(KST) < job["next_retry_at"]:
                return {
                    "manager_id": manager_id,
                    "manager_name": manager_name,
                    "manager_color": manager_color,
                    "mode": state.lower(),
                    "completed_path": [],
                    "remaining_path": [],
                    "distance_m": 0,
                    "duration_ms": 0,
                    "completed_stops": len(completed),
                    "remaining_stops": len(remaining),
                    "toll_fare": 0,
                    "fuel_price_naver": 0,
                    "fuel_price_opinet": _latest_opinet_fuel_price(),
                    "origin_name": origin["name"],
                    "source": "unavailable",
                    "completed_stop_ids": [s["id"] for s in completed],
                    "remaining_stop_ids": [s["id"] for s in remaining],
                    "payload": {"status": "retry_wait"},
                    "status": "failed_retryable",
                }

    if state == "PREVIEW" and trigger_reason == "api_read" and not force:
        return {
            "manager_id": manager_id,
            "manager_name": manager_name,
            "manager_color": manager_color,
            "mode": state.lower(),
            "completed_path": [],
            "remaining_path": [],
            "distance_m": 0,
            "duration_ms": 0,
            "completed_stops": 0,
            "remaining_stops": len(remaining),
            "toll_fare": 0,
            "fuel_price_naver": 0,
            "fuel_price_opinet": _latest_opinet_fuel_price(),
            "origin_name": origin["name"],
            "source": "pending",
            "completed_stop_ids": [],
            "remaining_stop_ids": [s["id"] for s in remaining],
            "payload": {"note": "preview route not auto-calculated"},
            "status": "pending",
        }

    completed_route = {
        "path": [],
        "distance_m": 0,
        "duration_ms": 0,
        "toll_fare": 0,
        "fuel_price_naver": 0,
        "source": "unavailable",
        "payloads": [],
        "status": "not_needed",
        "last_error": None,
        "last_error_payload": {},
    }
    remaining_route = {
        "path": [],
        "distance_m": 0,
        "duration_ms": 0,
        "toll_fare": 0,
        "fuel_price_naver": 0,
        "source": "unavailable",
        "payloads": [],
        "status": "not_needed",
        "last_error": None,
        "last_error_payload": {},
    }

    if completed:
        completed_route = _compute_route_batched(origin, completed)

    rem_origin = origin
    if completed:
        last = completed[-1]
        rem_origin = {
            "name": "last_completed",
            "latitude": last["latitude"],
            "longitude": last["longitude"],
        }

    if remaining:
        remaining_route = _compute_route_batched(rem_origin, remaining)

    fuel_price_opinet = _latest_opinet_fuel_price()
    overall_distance = completed_route["distance_m"] + remaining_route["distance_m"]
    overall_duration = completed_route["duration_ms"] + remaining_route["duration_ms"]
    overall_toll = completed_route["toll_fare"] + remaining_route["toll_fare"]
    overall_fuel_naver = completed_route["fuel_price_naver"] + remaining_route["fuel_price_naver"]

    has_any_path = bool(completed_route["path"] or remaining_route["path"])
    overall_source = "naver" if has_any_path else "unavailable"

    payload = {
        "manager_id": manager_id,
        "manager_name": manager_name,
        "manager_color": manager_color,
        "mode": state.lower(),
        "completed_path": completed_route["path"],
        "remaining_path": remaining_route["path"],
        "distance_m": overall_distance,
        "duration_ms": overall_duration,
        "completed_stops": len(completed),
        "remaining_stops": len(remaining),
        "toll_fare": overall_toll,
        "fuel_price_naver": overall_fuel_naver,
        "fuel_price_opinet": fuel_price_opinet,
        "origin_name": origin["name"],
        "source": overall_source,
        "completed_stop_ids": [s["id"] for s in completed],
        "remaining_stop_ids": [s["id"] for s in remaining],
        "payload": {
            "completed_raw": completed_route["payloads"],
            "remaining_raw": remaining_route["payloads"],
        },
        "status": "ready"
        if has_any_path
        else (
            remaining_route["status"]
            if remaining_route["status"] != "not_needed"
            else completed_route["status"]
        ),
    }

    if has_any_path or state == "RESULT":
        _cache_put(route_key, state, stop_signature, payload)
        _snapshot_insert(target, manager_id, state, trigger_reason, payload)
        _job_state_upsert(target, manager_id, state, stop_signature, route_key, "ready")
    else:
        prev = _job_state_get(target, manager_id, state)
        retry_count = (prev["retry_count"] + 1) if prev and prev.get("status") == "failed_retryable" else 1
        status = payload["status"] if payload["status"] in ("failed_retryable", "failed_final") else "failed_retryable"
        next_retry_at = _next_retry_time(retry_count) if status == "failed_retryable" else None
        _job_state_upsert(
            target,
            manager_id,
            state,
            stop_signature,
            route_key,
            status=status,
            retry_count=retry_count if status == "failed_retryable" else 0,
            next_retry_at=next_retry_at,
            last_error="route unavailable",
            last_error_payload=payload.get("payload", {}),
        )

    return payload


def collect_routes_for_date(target: date_type, force: bool = False, trigger_reason: str = "collector_tick") -> dict:
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
                origin=origin,
                origin_sig=origin_sig,
                manager_id=manager_id,
                manager_name=payload["manager_name"],
                manager_color=payload["manager_color"],
                manager_stops=payload["items"],
                force=force,
                trigger_reason=trigger_reason,
            )
        )

    return {
        "date": target.isoformat(),
        "state": state,
        "source": source,
        "routes": routes,
    }


def get_routes(target: date_type, force: bool = False) -> dict:
    return collect_routes_for_date(target, force=force, trigger_reason="api_read")


def get_route(target: date_type, manager_id: int, force: bool = False) -> dict:
    all_routes = collect_routes_for_date(target, force=force, trigger_reason="api_single_read")
    for route in all_routes["routes"]:
        if int(route["manager_id"]) == int(manager_id):
            return route
    return {
        "manager_id": manager_id,
        "manager_name": None,
        "manager_color": None,
        "mode": all_routes["state"].lower(),
        "completed_path": [],
        "remaining_path": [],
        "distance_m": 0,
        "duration_ms": 0,
        "completed_stops": 0,
        "remaining_stops": 0,
        "toll_fare": 0,
        "fuel_price_naver": 0,
        "fuel_price_opinet": None,
        "origin_name": None,
        "source": "unavailable",
        "completed_stop_ids": [],
        "remaining_stop_ids": [],
        "payload": {},
        "status": "failed_final",
    }


def force_refresh(target: date_type, manager_id: int) -> dict:
    return get_route(target, manager_id, force=True)
