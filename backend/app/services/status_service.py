from datetime import date as date_type, datetime

from app.services import day_aggregate, day_cache
from app.services.day_aggregate import KST


def get_cutoff_at(target: date_type) -> datetime:
    """(하위 호환) 기본 마감 시각. 실제 판정은 day_aggregate.resolve_cutoff(스케줄 기준)."""
    return day_aggregate.cutoff_from_schedule(None, target)[0]


def get_status(target: date_type) -> dict:
    now = datetime.now(KST)
    agg = day_cache.get_day(target, now)
    return day_aggregate.status_view(agg, now)
