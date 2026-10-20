from datetime import datetime, timedelta, timezone
import logging
import os
import time

from app.services import fuel_price_service, route_leg_service, routes_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("route_collector")
KST = timezone(timedelta(hours=9))

# 배송 처리 시간대 (운영시간) - 이 시간에만 변경 감지 + 경로 갱신
ROUTE_ACTIVE_START_HOUR = 6   # 오전 6시
ROUTE_ACTIVE_END_HOUR = 17    # 오후 5시 (17시 미포함)


def today_kst():
    return datetime.now(KST).date()


def is_delivery_hours() -> bool:
    now = datetime.now(KST)
    return ROUTE_ACTIVE_START_HOUR <= now.hour < ROUTE_ACTIVE_END_HOUR


def main():
    interval_active = int(os.environ.get("ROUTE_COLLECTOR_INTERVAL_SEC", "180"))
    interval_idle = int(os.environ.get("ROUTE_COLLECTOR_INTERVAL_IDLE_SEC", "1800"))
    logger.info(
        "route collector start: active_interval=%ss (%02d:00~%02d:00 KST), idle_interval=%ss",
        interval_active, ROUTE_ACTIVE_START_HOUR, ROUTE_ACTIVE_END_HOUR, interval_idle,
    )

    while True:
        try:
            fuel_price_service.ensure_today()   # 하루 1번 오피넷 유가 수집
        except Exception as exc:  # noqa: BLE001
            logger.warning("opinet fetch failed: %s", exc)
        interval = interval_active if is_delivery_hours() else interval_idle
        # [S3-P2d-2a] 실제 경로 구간: 새로 완료된 곳만 Directions 5로 이어 붙임 (새 완료 없으면 호출 0, 어제분은 자정 직후 마무리용)
        for d in (today_kst() - timedelta(days=1), today_kst()):
            try:
                r = route_leg_service.collect(d)
                if r["calls"] or r.get("stopped", "").startswith("NAVER"):
                    logger.info("route legs: %s", r)
            except Exception as exc:  # noqa: BLE001
                logger.exception("route legs failed: %s", exc)        
        try:
            if is_delivery_hours():
                target = today_kst()
                result = routes_service.collect_routes_for_date(
                    target,
                    force=False,
                    trigger_reason="collector_tick",
                )
                logger.info(
                    "collector ok: date=%s state=%s routes=%s",
                    result["date"], result["state"], len(result["routes"]),
                )
            else:
                logger.info("collector idle: outside delivery hours, skipping")
        except Exception as exc:  # noqa: BLE001
            logger.exception("collector failed: %s", exc)

        time.sleep(interval)


if __name__ == "__main__":
    main()

