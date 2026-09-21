from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from sqlalchemy import bindparam, text

from app.database import get_engine

# 마감 정책 (프로토타입 단순 버전): 배송일 전날 14:30 KST
# → 이후 business_calendar 도입 시 영업일 정책으로 확장 (v7)
KST = timezone(timedelta(hours=9))
CUTOFF_HOUR = 14
CUTOFF_MINUTE = 30


def get_cutoff_at(target: date_type) -> datetime:
    """배송일의 마감 시각 = 전날 14:30 KST."""
    cutoff_date = target - timedelta(days=1)
    return datetime(
        cutoff_date.year, cutoff_date.month, cutoff_date.day,
        CUTOFF_HOUR, CUTOFF_MINUTE, tzinfo=KST,
    )


def get_status(target: date_type) -> dict:
    """상태 판별 (delivery 집계 1회 + 시간 비교). SELECT만."""
    now = datetime.now(KST)
    cutoff_at = get_cutoff_at(target)

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text(
            """
            SELECT COUNT(DISTINCT d.id)                                                    AS total,
                   COUNT(DISTINCT CASE WHEN d.delivered_at IS NOT NULL THEN d.id END)      AS completed,
                   COUNT(DISTINCT CASE WHEN d.manager_id IS NULL THEN d.id END)            AS unassigned
            FROM delivery d
            WHERE d.date = :d
              AND d.deleted_at IS NULL
            """
        ), {"d": target}).fetchone()

    total = int(row[0] or 0)
    completed = int(row[1] or 0)
    unassigned = int(row[2] or 0)

    if total == 0:
        state = "NONE"
    elif now < cutoff_at:
        state = "PREVIEW"
    elif completed < total:
        state = "LIVE"
    else:
        state = "RESULT"

    return {
        "date": target.isoformat(),
        "state": state,
        "cutoff_at": cutoff_at.isoformat(),
        "now": now.isoformat(),
        "progress": {
            "completed": completed,
            "total": total,
            "unassigned": unassigned,
        },
    }
