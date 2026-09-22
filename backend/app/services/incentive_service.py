from datetime import date as date_type

from sqlalchemy import bindparam, text

from app.database import get_engine

LINEUP_IDS = (2, 4, 23, 29)


def product_incentive(q: int) -> int:
    """제품수 인센티브 (v7 §5)."""
    if q < 300:  return 0
    if q < 370:  return 50 * q
    if q < 440:  return 70 * q
    return 90 * q


def account_incentive(c: int) -> int:
    """고객사수 인센티브 (v7 §5)."""
    if c < 40:   return 0
    if c < 45:   return 300 * c
    if c < 50:   return 400 * c
    return 500 * c


def _fetch(target: date_type, manager_id: int | None):
    """매니저별 (Stops, 식수, 고객사수) 집계 — 순매출 라인업 (2,4,23,29) 한정."""
    sql = """
        SELECT d.manager_id                       AS manager_id,
               COUNT(DISTINCT d.id)               AS stops,
               COALESCE(SUM(od.quantity), 0)      AS meals,
               COUNT(DISTINCT o.account_id)       AS accounts
        FROM delivery d
        JOIN orders o
          ON o.delivery_date = d.date
         AND o.address_id    = d.address_id
         AND o.deleted_at IS NULL
        JOIN `order-details` od
          ON od.order_id  = o.id
         AND od.is_refund = 0
         AND od.deleted_at IS NULL
         AND od.product_id IN :lineups
        WHERE d.date = :d
          AND d.deleted_at IS NULL
          AND d.manager_id IS NOT NULL
    """
    params = {"d": target, "lineups": list(LINEUP_IDS)}
    if manager_id is not None:
        sql += " AND d.manager_id = :mid"
        params["mid"] = manager_id
    sql += " GROUP BY d.manager_id ORDER BY d.manager_id"

    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(
            text(sql).bindparams(bindparam("lineups", expanding=True)),
            params,
        ).fetchall()


def _safe_fetch(target, manager_id):
    """터널 실패 시 1회 재시도 (Step 2-5 표준 패턴)."""
    try:
        return _fetch(target, manager_id)
    except Exception:
        import app.database as db
        try:
            db._get_tunnel()
        except Exception:
            pass
        db._engine = None
        return _fetch(target, manager_id)


def _build_row(row) -> dict:
    q = int(row.meals or 0)
    c = int(row.accounts or 0)
    prod = product_incentive(q)
    acct = account_incentive(c)
    return {
        "manager_id":         int(row.manager_id),
        "stops":              int(row.stops or 0),
        "meals":              q,
        "accounts":           c,
        "product_incentive":  prod,
        "account_incentive":  acct,
        "total_incentive":    prod + acct,
    }


def get_incentive(target: date_type, manager_id: int) -> dict:
    rows = _safe_fetch(target, manager_id)
    if not rows:
        return {
            "date": target.isoformat(), "manager_id": manager_id,
            "stops": 0, "meals": 0, "accounts": 0,
            "product_incentive": 0, "account_incentive": 0, "total_incentive": 0,
        }
    return {"date": target.isoformat(), **_build_row(rows[0])}


def get_incentive_all(target: date_type) -> dict:
    rows = _safe_fetch(target, None)
    items = [_build_row(r) for r in rows]
    return {
        "date": target.isoformat(),
        "managers": items,
        "total_incentive_sum": sum(x["total_incentive"] for x in items),
    }
