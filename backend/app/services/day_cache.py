"""S0-P4.9 하루 집계 캐시 (Redis).

- 카드·지도·경로·기간 매출이 모두 get_day()를 거친다 → 같은 날짜는 TTL 동안 1번만 계산
- 키에 직원식 대상 서명을 넣어 설정 변경 시 자동으로 새 키 사용
- Redis 장애 시 캐시 없이 계산 (기존과 동일 동작)
"""
from __future__ import annotations

import hashlib
import logging
import os
import pickle
import threading
from datetime import date as date_type, datetime, timedelta

from app.services import day_aggregate
from app.services.day_aggregate import KST

logger = logging.getLogger("day_cache")

VERSION = "v4"          # v4: 배송 순서(seq), 배송시간 파싱 보강
TTL_TODAY = 20
TTL_RECENT = 600
TTL_OLD = 21600
RECENT_DAYS = 3

_client = None
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _redis():
    global _client
    if _client is None:
        import redis
        _client = redis.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://redis:6379/0"),
            socket_timeout=1, socket_connect_timeout=1,
        )
    return _client


def ttl_for(target: date_type, today: date_type) -> int:
    if target >= today:
        return TTL_TODAY
    if target >= today - timedelta(days=RECENT_DAYS):
        return TTL_RECENT
    return TTL_OLD


def _targets_sig() -> str:
    t = day_aggregate.internal_targets()
    src = ",".join(map(str, sorted(t["address_ids"]))) + "|" + ",".join(map(str, sorted(t["account_ids"])))
    return hashlib.sha1(src.encode()).hexdigest()[:10]


def cache_key(target: date_type, sig: str) -> str:
    return f"dash:day:{VERSION}:{target.isoformat()}:{sig}"


def _get(key: str):
    try:
        raw = _redis().get(key)
        return pickle.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        logger.warning("redis get 실패 - 캐시 없이 진행", exc_info=True)
        return None


def _set(key: str, value, ttl: int) -> None:
    try:
        _redis().setex(key, ttl, pickle.dumps(value))
    except Exception:  # noqa: BLE001
        logger.warning("redis set 실패", exc_info=True)


def _lock_for(key: str) -> threading.Lock:
    with _locks_guard:
        if len(_locks) > 500:
            _locks.clear()
        return _locks.setdefault(key, threading.Lock())


def _compute(target: date_type, now: datetime) -> dict:
    from app.database import get_engine

    def run():
        with get_engine().connect() as conn:
            return day_aggregate.build_day(conn, target, now=now)

    try:
        return run()
    except Exception:
        import app.database as db
        try:
            db._get_tunnel()
        except Exception:
            pass
        db._engine = None
        return run()


def get_day(target: date_type, now: datetime | None = None) -> dict:
    now = now or datetime.now(KST)
    key = cache_key(target, _targets_sig())
    hit = _get(key)
    if hit is not None:
        return hit
    with _lock_for(key):
        hit = _get(key)
        if hit is not None:
            return hit
        agg = _compute(target, now)
        _set(key, agg, ttl_for(target, now.date()))
        return agg
