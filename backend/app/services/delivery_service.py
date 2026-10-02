from datetime import date as date_type

from app.services import day_aggregate, day_cache
from app.services.day_aggregate import LINEUP_IDS, normalize_delivery_hour  # noqa: F401 (하위 호환)


def get_delivery_day(target: date_type) -> dict:
    """카드·지도·표 모두 day_aggregate 단일 집계 (캐시 경유)."""
    return day_aggregate.delivery_view(day_cache.get_day(target))
