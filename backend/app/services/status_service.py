from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from sqlalchemy import bindparam, text

from app.database import get_engine, _get_tunnel

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


def _fetch_all(target: date_type) -> dict:
    """쿼리 3종을 '하나의 연결 안에서' 모두 실행 (스코프 버그 제거)."""
    engine = get_engine()
    with engine.connect() as conn:
        # 1) delivery 기반 집계 (+ orders 존재 여부)
        main_row = conn.execute(text(
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

        # 2) delivery가 없을 때만 — 주문 기반 예상 집계
        estimate_row = None
        if int(main_row[0] or 0) == 0:
            estimate_row = conn.execute(text(
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

    return {"main": main_row, "estimate": estimate_row}


def get_status(target: date_type) -> dict:
    now = datetime.now(KST)
    cutoff_at = get_cutoff_at(target)
    today = now.date()

    # ---- 쿼리 실행 (실패 시 터널 복구 + 엔진 리셋 후 1회 재시도) ----
    try:
        data = _fetch_all(target)
    except Exception:
        import app.database as db
        try:
            db._get_tunnel()      # 터널 죽었으면 재시작
        except Exception:
            pass
        db._engine = None         # 엔진 재생성 (터널 포트 변경 대응)
        data = _fetch_all(target)

    main_row = data["main"]
    total = int(main_row[0] or 0)
    completed = int(main_row[1] or 0)
    unassigned = int(main_row[2] or 0)
    orders_count = int(main_row[3] or 0)
    incomplete = total - completed

    # ---- 판별 (NONE 우선 → 일자 우선) ----
    if now < cutoff_at:
        state = "PREVIEW"                      # 1) 마감 전
    elif total == 0 and orders_count == 0:
        state = "NONE"                         # 2) 둘 다 없음
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

    # ---- PREVIEW 집계원 분기 ----
    progress = {"completed": completed, "total": total, "unassigned": unassigned}
    estimate = None
    if state == "PREVIEW":
        if total > 0:
            pass                               # delivery 기반 (기존 값 그대로)
        elif data["estimate"] is not None:
            e = data["estimate"]
            estimate = {
                "total": int(e[0] or 0),
                "estimated_meals": int(e[1] or 0),
                "estimated_accounts": int(e[2] or 0),
                "estimated_net_revenue": int(e[3] or 0),
            }
            progress = {"completed": 0, "total": estimate["total"], "unassigned": 0}

    return {
        "date": target.isoformat(),
        "state": state,
        "incomplete": incomplete if state == "RESULT" else 0,
        "cutoff_at": cutoff_at.isoformat(),
        "now": now.isoformat(),
        "progress": progress,
        "estimate": estimate,
    }
