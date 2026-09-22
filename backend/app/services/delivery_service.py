from datetime import date as date_type

from sqlalchemy import bindparam, text

from app.database import get_engine

# 대상 라인업 (v7 확정: 2=석식, 4=가정식, 23=프레시밀, 29=라이트밀)
LINEUP_IDS = (2, 4, 23, 29)


def get_delivery_day(target: date_type) -> dict:
    """날짜별 배송현황 + 지도용 stop points."""
    engine = get_engine()
    with engine.connect() as conn:
        # 1) 매니저별 집계
        rows = conn.execute(text(
            """
            SELECT d.manager_id,
                   m.name  AS manager_name,
                   m.color AS manager_color,
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
            WHERE d.date = :d
              AND d.deleted_at IS NULL
            GROUP BY d.manager_id, od.product_id, p.name
            """
        ).bindparams(bindparam("lineups", expanding=True)),
          {"d": target, "lineups": list(LINEUP_IDS)}).fetchall()

        # 3) 전체 요약
        summary_row = conn.execute(text(
            """
            SELECT COUNT(DISTINCT d.id)                    AS stops,
                   COALESCE(SUM(od.quantity), 0)           AS meals,
                   COUNT(DISTINCT o.account_id)            AS accounts,
                   SUM(CASE WHEN d.manager_id IS NULL THEN 1 ELSE 0 END)       AS unassigned_stops,
                   COUNT(DISTINCT CASE WHEN d.delivered_at IS NOT NULL THEN d.id END) AS completed_stops
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
            WHERE d.date = :d
              AND d.deleted_at IS NULL
            """
        ).bindparams(bindparam("lineups", expanding=True)),
          {"d": target, "lineups": list(LINEUP_IDS)}).fetchone()

        # 4) 지도용 stop points (배송지 단위)
        stop_rows = conn.execute(text(
            """
            SELECT d.id                            AS delivery_id,
                   d.address_id                    AS address_id,
                   d.manager_id                    AS manager_id,
                   m.name                          AS manager_name,
                   m.color                         AS manager_color,
                   a.name                          AS address_name,
                   a.latitude                      AS latitude,
                   a.longitude                     AS longitude,
                   a.delivery_time                 AS delivery_time,
                   od.product_id                   AS product_id,
                   p.name                          AS product_name,
                   COALESCE(SUM(od.quantity), 0)   AS qty,
                   COUNT(DISTINCT o.account_id)    AS accounts
            FROM delivery d
            JOIN addresses a
              ON a.id = d.address_id
            JOIN orders o
              ON o.delivery_date = d.date
             AND o.address_id    = d.address_id
             AND o.deleted_at IS NULL
            JOIN `order-details` od
              ON od.order_id = o.id
             AND od.is_refund = 0
             AND od.deleted_at IS NULL
             AND od.product_id IN :lineups
            LEFT JOIN products p
              ON p.id = od.product_id
            LEFT JOIN manager m
              ON m.id = d.manager_id
            WHERE d.date = :d
              AND d.deleted_at IS NULL
              AND a.latitude IS NOT NULL
              AND a.longitude IS NOT NULL
            GROUP BY d.id, d.address_id, d.manager_id, m.name, m.color,
                     a.name, a.latitude, a.longitude, a.delivery_time,
                     od.product_id, p.name
            ORDER BY d.manager_id NULLS LAST, d.id
            """
        ).bindparams(bindparam("lineups", expanding=True)),
          {"d": target, "lineups": list(LINEUP_IDS)}).fetchall()

    # 라인업 데이터 매니저별 그룹화
    lineup_map: dict[int | None, dict] = {}
    for manager_id, pid, pname, qty, amount in lineup_rows:
        lineup_map.setdefault(manager_id, {})[str(pid)] = {
            "name": pname or str(pid),
            "qty": int(qty),
            "amount": int(amount),
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

    # stop points 그룹화
    stop_map: dict[str, dict] = {}
    for row in stop_rows:
        key = str(row.delivery_id)
        stop = stop_map.setdefault(key, {
            "delivery_id": key,
            "address_id": row.address_id,
            "address_name": row.address_name,
            "latitude": float(row.latitude),
            "longitude": float(row.longitude),
            "delivery_time": row.delivery_time,
            "manager_id": row.manager_id,
            "manager_name": row.manager_name,
            "manager_color": row.manager_color,
            "accounts": int(row.accounts or 0),
            "lineups": {},
        })
        stop["lineups"][str(row.product_id)] = {
            "name": row.product_name or str(row.product_id),
            "qty": int(row.qty or 0),
        }

    # 각 stop의 총 식수
    for stop in stop_map.values():
        stop["meals"] = sum(item["qty"] for item in stop["lineups"].values())

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
        "unassigned": {"stops": int(summary_row[3] or 0)},
        "stops": list(stop_map.values()),
    }
