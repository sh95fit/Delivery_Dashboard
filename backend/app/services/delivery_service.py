from datetime import date as date_type

from app.database import get_engine
from app.services import day_aggregate
from app.services.day_aggregate import LINEUP_IDS, normalize_delivery_hour  # noqa: F401 (하위 호환)


def _build(target: date_type) -> dict:
    with get_engine().connect() as conn:
        return day_aggregate.build_day(conn, target)


def get_delivery_day(target: date_type) -> dict:
    """카드·지도·표 모두 day_aggregate 단일 집계 사용."""
    try:
        agg = _build(target)
    except Exception:
        import app.database as db
        try:
            db._get_tunnel()
        except Exception:
            pass
        db._engine = None
        agg = _build(target)
    return day_aggregate.delivery_view(agg)
