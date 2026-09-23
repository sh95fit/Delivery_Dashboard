from datetime import datetime, timedelta, timezone
import logging
import os
import time

from app.services import routes_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("route_collector")
KST = timezone(timedelta(hours=9))


def today_kst():
    return datetime.now(KST).date()


def main():
    interval = int(os.environ.get("ROUTE_COLLECTOR_INTERVAL_SEC", "60"))
    logger.info("route collector start: interval=%s sec", interval)

    while True:
        try:
            target = today_kst()
            result = routes_service.collect_routes_for_date(
                target,
                force=False,
                trigger_reason="collector_tick",
            )
            logger.info(
                "collector ok: date=%s state=%s routes=%s",
                result["date"],
                result["state"],
                len(result["routes"]),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("collector failed: %s", exc)

        time.sleep(interval)


if __name__ == "__main__":
    main()
