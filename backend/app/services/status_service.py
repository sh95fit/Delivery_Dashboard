from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from sqlalchemy import bindparam, text

from app.database import get_engine

# 마감 정책 (프로토타입 단순 버전): 배송일 전날 14:30 KST
# → 이후 business_calendar 도입 시 영업일 정책으로 확장 (v7)
KST = timezone(timedelta(hours=9))
CUTOFF_HOUR = 14
CUTOFF_MINUTE = 30
LINEUP_IDS = (2, 4, 23, 29)


def get_cutoff_at(target: date_type) -> datetime:
    """배송일의 마감 시각 = 전날 14:30 KST."""
    cutoff_date = target - timedelta(days=1)
    return datetime(
        cutoff_date.year, cutoff_date.month, cutoff_date.day,
        CUTOFF_HOUR, CUTOFF_MINUTE, tzinfo=KST,
    )


def _get_preview_estimate(conn, target: date_type) -> dict:
    """배송 일감 생성 전 — 주문 기반 예상 배송지·식수·고객사·순매출 집계."""
    row = conn.execute(text(
        """
        SELECT COUNT(DISTINCT o.address_id)                   AS stops,
               COALESCE(SUM(od.quantity), 0)                  AS meals,
               COUNT(DISTINCT o.account_id)                   AS accounts,
               COALESCE(ROUND(SUM(od.total_amount) / 1.1), 0) AS net_revenue
        FROM orders o
        JOIN `order-details` od
          ON od.order_id = o.id
         AND od.is_refund = 0
         AND od.deleted_at IS NULL
         AND od.product_id IN :lineups
        WHERE o.delivery_date = :d
          AND o.deleted_at IS NULL
        """
    ).bindparams(bindparam("lineups", expanding=True)),
      {"d": target, "lineups": list(LINEUP_IDS)}).fetchone()

    return {
        "total": int(row[0] or 0),            # 예상 Stops (배송지 수)
        "estimated_meals": int(row[1] or 0),
        "estimated_accounts": int(row[2] or 0),
        "estimated_net_revenue": int(row[3] or 0),
    }


def get_status(target: date_type) -> dict:
    """상태 판별 — NONE 우선 → 일자 우선. PREVIEW는 delivery 유무에 따라 집계원이 달라짐."""
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
        state = "PREVIEW"                      # 1) 마감 전
    elif total == 0 and orders_count == 0:
        state = "NONE"                         # 2) 둘 다 없음 (과거·미래 무관)
    elif target < today:
        state = "RESULT"                       # 3) 과거 — 일자 우선
    elif target == today:
        if total > 0 and completed >= total:
            state = "RESULT"
        elif total > 0:
            state = "LIVE"
        elif orders_count > 0:
            state = "PREVIEW"
        else:
            state = "NONE"
    else:
        state = "PREVIEW"                      # 5) 미래

    # ---- PREVIEW: delivery 유무에 따라 집계원 결정 ----
    progress = {
        "completed": completed,
        "total": total,
        "unassigned": unassigned,
    }
    estimate = None
    if state == "PREVIEW":
        if total > 0:
            # delivery가 이미 있음 → delivery 기반 (기존 값 그대로)
            pass
        elif orders_count > 0:
            # delivery 없음 → 주문 기반 예상 집계
            estimate = _get_preview_estimate(conn, target)
            progress = {
                "completed": 0,
                "total": estimate["total"],    # 예상 배송지 수
                "unassigned": 0,
            }
        # 둘 다 없으면 NONE이라 여기 안 옴

    return {
        "date": target.isoformat(),
        "state": state,
        "incomplete": incomplete if state == "RESULT" else 0,
        "cutoff_at": cutoff_at.isoformat(),
        "now": now.isoformat(),
        "progress": progress,
        "estimate": estimate,                  # delivery 없는 PREVIEW에서만 존재
    }
