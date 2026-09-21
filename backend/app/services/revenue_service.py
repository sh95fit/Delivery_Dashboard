from datetime import date as date_type

from sqlalchemy import bindparam, text

from app.database import get_engine

LINEUP_IDS = (2, 4, 23, 29)


def get_revenue_summary(start: date_type, end: date_type) -> dict:
    """기간 순매출 집계. JOIN 1회로 매니저×라인업 집계 → 나머지는 파이썬 합산. SELECT만."""
    engine = get_engine()
    with engine.connect() as conn:
        # 단일 기본 집계: 매니저 × 라인업 (JOIN 1회)
        rows = conn.execute(text(
            """
            SELECT d.manager_id,
                   m.name                         AS manager_name,
                   od.product_id,
                   p.name                         AS product_name,
                   COUNT(DISTINCT d.id)           AS stops,
                   od.quantity                    AS qty,
                   ROUND(od.total_amount / 1.1)   AS amount
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
            LEFT JOIN products p
              ON p.id = od.product_id
            WHERE d.date BETWEEN :start AND :end
              AND d.deleted_at IS NULL
            """
        ).bindparams(bindparam("lineups", expanding=True)),
          {"start": start, "end": end, "lineups": list(LINEUP_IDS)}).fetchall()

        # 고객사 수 (별도: delivery 기준 DISTINCT account) — 1개 가벼운 쿼리
        account_rows = conn.execute(text(
            """
            SELECT d.manager_id,
                   COUNT(DISTINCT a.account_id) AS accounts
            FROM delivery d
            LEFT JOIN addresses a ON a.id = d.address_id
            WHERE d.date BETWEEN :start AND :end
              AND d.deleted_at IS NULL
            GROUP BY d.manager_id
            """
        ),
          {"start": start, "end": end}).fetchall()
        accounts_map = {r[0]: int(r[1]) for r in account_rows}

    # ---- 파이썬 집계 (행 수: 매니저 15 × 라인업 4 ≈ 60행 수준, 비용 무시) ----
    from collections import defaultdict

    by_manager_acc: dict = defaultdict(lambda: {
        "manager_id": None, "manager_name": None, "stops_set": set(),
        "meals": 0, "net_revenue": 0, "lineups": defaultdict(lambda: {"name": "", "qty": 0, "amount": 0}),
    })
    lineup_acc: dict = defaultdict(lambda: {"name": "", "qty": 0, "amount": 0})
    total_stops_set: set = set()
    total_meals = 0
    total_net = 0

    for manager_id, mname, pid, pname, stops, qty, amount in rows:
        acc = by_manager_acc[manager_id]
        acc["manager_id"] = manager_id
        acc["manager_name"] = mname
        # stops: d.id DISTINCT가 필요하나 그룹핑이 manager×product라 set으로 처리
        acc["stops_set"].add((manager_id, stops))  # 실제 distinct 처리는 아래 참고
        qty_i, amount_i = int(qty or 0), int(amount or 0)
        acc["meals"] += qty_i
        acc["net_revenue"] += amount_i
        lu = acc["lineups"][str(pid)]
        lu["name"] = pname or str(pid)
        lu["qty"] += qty_i
        lu["amount"] += amount_i

        lu_all = lineup_acc[str(pid)]
        lu_all["name"] = pname or str(pid)
        lu_all["qty"] += qty_i
        lu_all["amount"] += amount_i

        total_meals += qty_i
        total_net += amount_i

    # ⚠️ stops 정확 산출: 위 rows는 (매니저×상품) 단위라 d.id 중복이 있음 → 별도 정확 집계 쿼리 1회
    stops_rows = conn.execute(text(
        """
        SELECT d.manager_id, COUNT(DISTINCT d.id) AS stops
        FROM delivery d
        WHERE d.date BETWEEN :start AND :end
          AND d.deleted_at IS NULL
        GROUP BY d.manager_id
        """
    ), {"start": start, "end": end}).fetchall()
    stops_map = {r[0]: int(r[1]) for r in stops_rows}

    total_stops = sum(stops_map.values())

    by_manager = []
    for manager_id, acc in by_manager_acc.items():
        by_manager.append({
            "manager_id": manager_id,
            "manager_name": acc["manager_name"],
            "stops": stops_map.get(manager_id, 0),
            "meals": acc["meals"],
            "accounts": accounts_map.get(manager_id, 0),
            "net_revenue": acc["net_revenue"],
            "lineups": {k: dict(v) for k, v in acc["lineups"].items()},
        })
    by_manager.sort(key=lambda x: x["net_revenue"], reverse=True)

    return {
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "total": {
            "net_revenue": total_net,
            "meals": total_meals,
            "stops": total_stops,
            "accounts": sum(accounts_map.values()),
        },
        "by_manager": by_manager,
        "by_lineup": {k: dict(v) for k, v in lineup_acc.items()},
    }
