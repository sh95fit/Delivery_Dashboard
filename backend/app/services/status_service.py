from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

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
    """상태 판별 — NONE 우선(데이터 없음) → 일자 우선(과거 RESULT) 순서."""
    now = datetime.now(KST)
    cutoff_at = get_cutoff_at(target)
    today = now.date()

    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text(
            """
            SELECT COUNT(DISTINCT d.id)                                                       AS total,
                   COUNT(DISTINCT CASE WHEN d.delivered_at IS NOT NULL THEN d.id END)         AS completed,
                   COUNT(DISTINCT CASE WHEN d.manager_id IS NULL THEN d.id END)               AS unassigned,
                   (SELECT COUNT(*) FROM orders o
                      WHERE o.delivery_date = :d AND o.deleted_at IS NULL)                    AS orders_count
            FROM delivery d
            WHERE d.date = :d
              AND d.deleted_at IS NULL
            """
        ), {"d": target}).fetchone()

    total = int(row[0] or 0)
    completed = int(row[1] or 0)
    unassigned = int(row[2] or 0)
    orders_count = int(row[3] or 0)
    incomplete = total - completed

    # ---- 판별 (NONE 우선 → 일자 우선) ----
    if now < cutoff_at:
        # 1) 마감 전
        state = "PREVIEW"
    elif total == 0 and orders_count == 0:
        # 2) 배송·주문 둘 다 없음 — 과거라도 NONE (공휴일·비영업일)
        state = "NONE"
    elif target < today:
        # 3) 과거 배송일 — 일자 우선: 미완료 있어도 RESULT
        state = "RESULT"
    elif target == today:
        # 4) 오늘
        if total > 0 and completed >= total:
            state = "RESULT"
        elif total > 0:
            state = "LIVE"
        elif orders_count > 0:
            state = "PREVIEW"      # 주문 확정, 배송 일감 미생성
        else:
            state = "NONE"
    else:
        # 5) 미래 배송일
        state = "PREVIEW"

    return {
        "date": target.isoformat(),
        "state": state,
        "incomplete": incomplete if state == "RESULT" else 0,
        "cutoff_at": cutoff_at.isoformat(),
        "now": now.isoformat(),
        "progress": {
            "completed": completed,
            "total": total,
            "unassigned": unassigned,
        },
    }
