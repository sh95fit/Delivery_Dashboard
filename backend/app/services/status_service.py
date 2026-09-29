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
    """쿼리 3종을 '하나의 연결 안에서' 모두 실행."""
    engine = get_engine()
    with engine.connect() as conn:
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

        estimate_row = None
        if datetime.now(KST) < get_cutoff_at(target):
            # 마감 전: 웹(orders) + 앱 개별 선택(selected_menus, 미전환) 합산.
            # 각 집계는 독립된 1행 스칼라 서브쿼리로 분리 (UNION 다중행 → 1242 에러 방지)
            estimate_row = conn.execute(text(
                """
                SELECT
                  (SELECT COUNT(DISTINCT addr.id) FROM orders o
                     JOIN addresses addr ON addr.id = o.address_id
                     WHERE o.delivery_date = :d AND o.deleted_at IS NULL) AS web_stops,
                  (SELECT COUNT(DISTINCT addr2.id) FROM selected_menus sm
                     JOIN schedules sc ON sc.id = sm.schedule_id AND sc.delivery_on = :d
                     JOIN order_profiles op ON op.id = sm.order_profile_id
                     JOIN addresses addr2 ON addr2.id = op.address_id
                     WHERE sm.order_id IS NULL AND sm.is_skipped = 0 AND op.deleted_at IS NULL) AS app_stops,
                  (SELECT COALESCE(SUM(od.quantity),0) FROM orders o
                     JOIN `order-details` od ON od.order_id = o.id
                       AND od.is_refund = 0 AND od.deleted_at IS NULL
                       AND od.product_id IN :lineups
                     WHERE o.delivery_date = :d AND o.deleted_at IS NULL) AS web_qty,
                  (SELECT COUNT(sm.id) FROM selected_menus sm
                     JOIN schedules sc ON sc.id = sm.schedule_id AND sc.delivery_on = :d
                     JOIN scheduled_menus smp ON smp.id = sm.scheduled_menu_id
                     WHERE sm.order_id IS NULL AND sm.is_skipped = 0
                       AND smp.product_id IN :lineups) AS app_qty,
                  (SELECT COUNT(DISTINCT o.account_id) FROM orders o
                     WHERE o.delivery_date = :d AND o.deleted_at IS NULL) AS web_accounts,
                  (SELECT COUNT(DISTINCT op.company_id) FROM selected_menus sm
                     JOIN schedules sc ON sc.id = sm.schedule_id AND sc.delivery_on = :d
                     JOIN order_profiles op ON op.id = sm.order_profile_id
                     WHERE sm.order_id IS NULL AND sm.is_skipped = 0 AND op.deleted_at IS NULL
                       AND op.company_id IS NOT NULL) AS app_accounts,
                  (SELECT COALESCE(ROUND(SUM(od.total_amount)/1.1),0) FROM orders o
                     JOIN `order-details` od ON od.order_id = o.id
                       AND od.is_refund = 0 AND od.deleted_at IS NULL
                       AND od.product_id IN :lineups
                     WHERE o.delivery_date = :d AND o.deleted_at IS NULL) AS net_revenue
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
                "estimated_meals": int(e[2] or 0) + int(e[3] or 0),
                "estimated_accounts": int(e[4] or 0) + int(e[5] or 0),
                "estimated_net_revenue": int(e[6] or 0),
                "web_qty": int(e[2] or 0),
                "app_qty": int(e[3] or 0),
                "web_stops": int(e[0] or 0),
                "app_stops": int(e[1] or 0),
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
