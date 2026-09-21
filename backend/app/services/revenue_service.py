from datetime import date as date_type

from sqlalchemy import bindparam, text

from app.database import get_engine

LINEUP_IDS = (2, 4, 23, 29)


def get_revenue_summary(start: date_type, end: date_type) -> dict:
    """기간 순매출 집계 (전체/노선별/라인업별). SELECT만."""
    engine = get_engine()
    with engine.connect() as conn:
        # 1) 전체 요약
        total_row = conn.execute(text(
            """
            SELECT COALESCE(ROUND(SUM(od.total_amount) / 1.1), 0) AS net_revenue,
                   COALESCE(SUM(od.quantity), 0)                  AS meals,
                   COUNT(DISTINCT d.id)                           AS stops,
                   COUNT(DISTINCT o.account_id)                   AS accounts
            FROM delivery d
            JOIN orders o
              ON o.delivery_date = d.date
             AND o.address_id    = d.address_id
             AND o.deleted_at IS NULL
            JOIN `order-details` od
              ON od.order_id = o.id
             AND od.is_refund = 0
             AND od.deleted_at IS NULL
             AND od.product_id IN :lineups
            WHERE d.date BETWEEN :start AND :end
              AND d.deleted_at IS NULL
            """
        ).bindparams(bindparam("lineups", expanding=True)),
          {"start": start, "end": end, "lineups": list(LINEUP_IDS)}).fetchone()

        # 2) 노선(매니저)별
        manager_rows = conn.execute(text(
            """
            SELECT d.manager_id,
                   m.name  AS manager_name,
                   COUNT(DISTINCT d.id)                           AS stops,
                   COALESCE(SUM(od.quantity), 0)                  AS meals,
                   COUNT(DISTINCT o.account_id)                   AS accounts,
                   COALESCE(ROUND(SUM(od.total_amount) / 1.1), 0) AS net_revenue
            FROM delivery d
            JOIN orders o
              ON o.delivery_date = d.date
             AND o.address_id    = d.address_id
             AND o.deleted_at IS NULL
            JOIN `order-details` od
              ON od.order_id = o.id
             AND od.is_refund = 0
             AND od.deleted_at IS NULL
             AND od.product_id IN :lineups
            LEFT JOIN manager m
              ON m.id = d.manager_id
            WHERE d.date BETWEEN :start AND :end
              AND d.deleted_at IS NULL
            GROUP BY d.manager_id, m.name
            ORDER BY net_revenue DESC
            """
        ).bindparams(bindparam("lineups", expanding=True)),
          {"start": start, "end": end, "lineups": list(LINEUP_IDS)}).fetchall()

        # 3) 매니저×라인업별 (드릴다운용)
        manager_lineup_rows = conn.execute(text(
            """
            SELECT d.manager_id,
                   od.product_id,
                   p.name                         AS product_name,
                   COALESCE(SUM(od.quantity), 0)  AS qty,
                   COALESCE(ROUND(SUM(od.total_amount) / 1.1), 0) AS amount
            FROM delivery d
            JOIN orders o
              ON o.delivery_date = d.date
             AND o.address_id    = d.address_id
             AND o.deleted_at IS NULL
            JOIN `order-details` od
              ON od.order_id = o.id
             AND od.is_refund = 0
             AND od.deleted_at IS NULL
             AND od.product_id IN :lineups
            LEFT JOIN products p ON p.id = od.product_id
            WHERE d.date BETWEEN :start AND :end
              AND d.deleted_at IS NULL
            GROUP BY d.manager_id, od.product_id, p.name
            """
        ).bindparams(bindparam("lineups", expanding=True)),
          {"start": start, "end": end, "lineups": list(LINEUP_IDS)}).fetchall()

        # 4) 라인업별 전체
        lineup_rows = conn.execute(text(
            """
            SELECT od.product_id,
                   p.name                        AS product_name,
                   COALESCE(SUM(od.quantity), 0) AS qty,
                   COALESCE(ROUND(SUM(od.total_amount) / 1.1), 0) AS amount
            FROM delivery d
            JOIN orders o
              ON o.delivery_date = d.date
             AND o.address_id    = d.address_id
             AND o.deleted_at IS NULL
            JOIN `order-details` od
              ON od.order_id = o.id
             AND od.is_refund = 0
             AND od.deleted_at IS NULL
             AND od.product_id IN :lineups
            LEFT JOIN products p ON p.id = od.product_id
            WHERE d.date BETWEEN :start AND :end
              AND d.deleted_at IS NULL
            GROUP BY od.product_id, p.name
            ORDER BY amount DESC
            """
        ).bindparams(bindparam("lineups", expanding=True)),
          {"start": start, "end": end, "lineups": list(LINEUP_IDS)}).fetchall()

    # 매니저별 라인업 그룹화
    ml_map: dict[int | None, dict] = {}
    for manager_id, pid, pname, qty, amount in manager_lineup_rows:
        ml_map.setdefault(manager_id, {})[str(pid)] = {
            "name": pname or str(pid), "qty": int(qty), "amount": int(amount),
        }

    by_manager = []
    for manager_id, mname, stops, meals, accounts, net in manager_rows:
        by_manager.append({
            "manager_id": manager_id,
            "manager_name": mname,
            "stops": int(stops),
            "meals": int(meals),
            "accounts": int(accounts),
            "net_revenue": int(net or 0),
            "lineups": ml_map.get(manager_id, {}),
        })

    by_lineup = {}
    for pid, pname, qty, amount in lineup_rows:
        by_lineup[str(pid)] = {"name": pname or str(pid), "qty": int(qty), "amount": int(amount)}

    return {
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "total": {
            "net_revenue": int(total_row[0] or 0),
            "meals": int(total_row[1] or 0),
            "stops": int(total_row[2] or 0),
            "accounts": int(total_row[3] or 0),
        },
        "by_manager": by_manager,
        "by_lineup": by_lineup,
    }
