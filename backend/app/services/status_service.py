from datetime import date as date_type, datetime

from app.database import get_engine
from app.services import day_aggregate
from app.services.day_aggregate import KST


def get_cutoff_at(target: date_type) -> datetime:
    """(하위 호환) 기본 마감 시각. 실제 판정은 day_aggregate.resolve_cutoff(스케줄 기준)."""
    return day_aggregate.cutoff_from_schedule(None, target)[0]


def _build(target: date_type, now: datetime) -> dict:
    with get_engine().connect() as conn:
        return day_aggregate.build_day(conn, target, now=now)


def get_status(target: date_type) -> dict:
    now = datetime.now(KST)
    try:
        agg = _build(target, now)
    except Exception:
        import app.database as db
        try:
            db._get_tunnel()
        except Exception:
            pass
        db._engine = None
        agg = _build(target, now)
    return day_aggregate.status_view(agg, now)
