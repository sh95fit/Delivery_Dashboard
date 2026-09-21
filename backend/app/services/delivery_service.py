from datetime import date as date_type

from sqlalchemy import text

from app.database import get_engine

from sqlalchemy import bindparam

# 대상 라인업 (v7 확정)
LINEUP_IDS = (2, 4, 23, 29)


def get_delivery_day(target: date_type) -> dict:
    """날짜별 배송현황 (Stops·식수·고객사·매니저별·라인업별). SELECT만."""
    engine = get_engine()
    with engine.connect() as conn:
        # 1) 매니저별 집계 (delivery × orders × order-details × manager)
        rows = conn.execute(text(
            """
            SELECT d.manager_id,
                   m.name  AS manager_name,
                   m.color AS manager_color,
                   COUNT(DISTINCT d.id)                          AS stops,
                   COALESCE(SUM(od.quantity), 0)                 AS meals,
                   COUNT(DISTINCT o.account_id)                  AS accounts,
                   COALESCE(ROUND(SUM(od.total_amount) / 1.1), 0) AS net_revenue
            FROM delivery d
            JOIN `order-details` od
                 ON od.order_id IN (
                      SELECT o.id FROM orders o
                      WHERE o.delivery_date = d.date
                        AND o.address_id   = d.address_id
                        AND o.deleted_at IS NULL
                 )
                AND od.is_refund = 0
                AND od.deleted_at IS NULL
                AND od.product_id IN :lineups
            LEFT JOIN manager m
                 ON m.id = d.manager_id
            WHERE d.date = :d
              AND d.deleted_at IS NULL
            GROUP BY d.manager_id, m.name, m.color
            ORDER BY stops DESC
            """
        ).bindparams(bindparam("lineups", expanding=True)),
          {"d": target, "lineups": list(LINEUP_IDS)}).fetchall()

        # 2) 라인업별 수량·금액 (매니저별)
        lineup_rows = conn.execute(text(
            """
            SELECT d.manager_id,
                   od.product_id,
                   p.name                       AS product_name,
                   COALESCE(SUM(od.quantity), 0) AS qty,
                   COALESCE(ROUND(SUM(od.total_amount) / 1.1), 0) AS amount
            FROM delivery d
            JOIN `order-details` od
                 ON od.order_id IN (
                      SELECT o.id FROM orders o
                      WHERE o.delivery_date = d.date
                        AND o.address_id   = d.address_id
                        AND o.deleted_at IS NULL
                 )
                AND od.is_refund = 0
                AND od.deleted_at IS NULL
                AND od.product_id IN :lineups
            LEFT JOIN products p ON p.id = od.product_id
            WHERE d.date = :d
              AND d.deleted_at IS NULL
            GROUP BY d.manager_id, od.product_id, p.name
            """
        ).bindparams(bindparam("lineups", expanding=True)),
          {"d": target, "lineups": list(LINEUP_IDS)}).fetchall()

        # 3) 전체 요약 + 미배정
        summary_row = conn.execute(text(
            """
            SELECT COUNT(DISTINCT d.id) AS stops,
                   COALESCE(SUM(od.quantity), 0) AS meals,
                   COUNT(DISTINCT o.account_id)  AS accounts,
                   SUM(CASE WHEN d.manager_id IS NULL THEN 1 ELSE 0 END) AS unassigned_stops,
                   SUM(CASE WHEN d.delivered_at IS NOT NULL THEN 1 ELSE 0 END) AS completed_stops
            FROM delivery d
            JOIN `order-details` od
                 ON od.order_id IN (
                      SELECT o.id FROM orders o
                      WHERE o.delivery_date = d.date
                        AND o.address_id   = d.address_id
                        AND o.deleted_at IS NULL
                 )
                AND od.is_refund = 0
                AND od.deleted_at IS NULL
                AND od.product_id IN :lineups
            WHERE d.date = :d
              AND d.deleted_at IS NULL
            """
        ).bindparams(bindparam("lineups", expanding=True)),
          {"d": target, "lineups": list(LINEUP_IDS)}).fetchone()

    # 라인업 데이터 매니저별 그룹화
    lineup_map: dict[int | None, dict] = {}
    for manager_id, pid, pname, qty, amount in lineup_rows:
        lineup_map.setdefault(manager_id, {})[str(pid)] = {
            "name": pname or str(pid), "qty": int(qty), "amount": int(amount),
        }

    managers = []
    for manager_id, mname, mcolor, stops, meals, accounts, net in rows:
        managers.append({
            "manager_id": manager_id,
            "manager_name": mname,
            "color": mcolor,
            "stops": int(stops),
            "meals": int(meals),
            "accounts": int(accounts),
            "net_revenue": int(net or 0),
            "lineups": lineup_map.get(manager_id, {}),
        })

    unassigned_meals = sum(
        lu.get("2", {}).get("qty", 0) for lu in []
    )  # placeholder (미사용)

    return {
        "date": target.isoformat(),
        "summary": {
            "stops": int(summary_row[0] or 0),
            "meals": int(summary_row[1] or 0),
            "accounts": int(summary_row[2] or 0),
            "completed_stops": int(summary_row[4] or 0),
            "unassigned_stops": int(summary_row[3] or 0),
        },
        "managers": managers,
        "unassigned": {
            "stops": int(summary_row[3] or 0),
        },
    }
