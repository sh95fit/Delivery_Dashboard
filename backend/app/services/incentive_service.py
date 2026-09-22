from datetime import date as date_type

from sqlalchemy import bindparam, text

from app.database import get_dash_engine, get_engine

LINEUP_IDS = (2, 4, 23, 29)
GAJUNG = 4
ADJUSTABLE_FIELDS = {"gajung_qty", "mil_qty", "collection_count", "stops", "accounts"}


# ---------- 산식 (2026-09 확정: 초과분 × 구간단가) ----------
def product_incentive(q: int) -> int:
    if q <= 300:
        return 0
    excess = q - 300
    rate = 50 if q <= 370 else 70 if q <= 440 else 90
    return excess * rate


def account_incentive(c: int) -> int:
    if c <= 40:
        return 0
    excess = c - 40
    rate = 300 if c <= 45 else 400 if c <= 50 else 500
    return excess * rate


# ---------- RDS 자동 집계 (배송지 기준 — LEFT JOIN으로 미연결 배송지도 포함) ----------
def _fetch_auto(target: date_type, manager_id: int | None):
    sql = """
        SELECT d.manager_id                          AS manager_id,
               COUNT(DISTINCT d.id)                  AS stops,
               COALESCE(SUM(CASE WHEN od.product_id = :gajung THEN od.quantity END), 0) AS gajung_qty,
               COALESCE(SUM(CASE WHEN od.product_id IN :mil THEN od.quantity END), 0)   AS mil_qty,
               COUNT(DISTINCT o.account_id)          AS accounts_distinct
        FROM delivery d
        LEFT JOIN orders o
          ON o.delivery_date = d.date
         AND o.address_id    = d.address_id
         AND o.deleted_at IS NULL
        LEFT JOIN `order-details` od
          ON od.order_id  = o.id
         AND od.is_refund = 0
         AND od.deleted_at IS NULL
         AND od.product_id IN :lineups
        WHERE d.date = :d
          AND d.deleted_at IS NULL
          AND d.manager_id IS NOT NULL
    """
    params: dict = {"d": target, "lineups": list(LINEUP_IDS), "gajung": GAJUNG,
                    "mil": [23, 29]}
    if manager_id is not None:
        sql += " AND d.manager_id = :mid"
        params["mid"] = manager_id
    sql += " GROUP BY d.manager_id ORDER BY d.manager_id"

    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(
            text(sql).bindparams(bindparam("lineups", expanding=True),
                                 bindparam("mil", expanding=True)),
            params,
        ).fetchall()


def _safe_fetch_auto(target, manager_id):
    try:
        return _fetch_auto(target, manager_id)
    except Exception:
        import app.database as db
        try:
            db._get_tunnel()
        except Exception:
            pass
        db._engine = None
        return _fetch_auto(target, manager_id)


# ---------- dash DB: 조정 이력 + 미지급 ----------
def _ensure_tables():
    engine = get_dash_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS incentive_adjustments (
                id SERIAL PRIMARY KEY,
                manager_id INTEGER NOT NULL,
                adj_date DATE NOT NULL,
                field VARCHAR(30) NOT NULL,
                value INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_by VARCHAR(255),
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS ix_adj_mgr_date
                ON incentive_adjustments (manager_id, adj_date);
            CREATE TABLE IF NOT EXISTS incentive_holds (
                id SERIAL PRIMARY KEY,
                manager_id INTEGER NOT NULL,
                hold_date DATE NOT NULL,
                reason TEXT NOT NULL,
                created_by VARCHAR(255),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                released_at TIMESTAMPTZ,
                UNIQUE(manager_id, hold_date)
            );
        """))
        conn.commit()


def _latest_adjustments(target: date_type, manager_id: int | None) -> dict:
    """(manager, date, field) 최신 조정값 — 이력은 행으로 보존."""
    _ensure_tables()
    engine = get_dash_engine()
    sql = """
        SELECT DISTINCT ON (manager_id, field)
               manager_id, field, value, reason, created_by, created_at
        FROM incentive_adjustments
        WHERE adj_date = :d
    """
    params: dict = {"d": target}
    if manager_id is not None:
        sql += " AND manager_id = :m"
        params["m"] = manager_id
    sql += " ORDER BY manager_id, field, created_at DESC, id DESC"

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    out: dict[int, dict[str, dict]] = {}
    for r in rows:
        out.setdefault(int(r.manager_id), {})[r.field] = {
            "value": int(r.value), "reason": r.reason,
            "created_by": r.created_by, "created_at": r.created_at.isoformat(),
        }
    return out


def set_adjustment(target: date_type, manager_id: int, field: str, value: int,
                   reason: str, email: str) -> None:
    if field not in ADJUSTABLE_FIELDS:
        raise ValueError(f"허용되지 않는 필드: {field}")
    _ensure_tables()
    engine = get_dash_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO incentive_adjustments
                   (manager_id, adj_date, field, value, reason, created_by)
            VALUES (:m, :d, :f, :v, :r, :by)
        """), {"m": manager_id, "d": target, "f": field, "v": value, "r": reason, "by": email})
        conn.commit()


def set_hold(target: date_type, manager_id: int, reason: str, email: str) -> None:
    _ensure_tables()
    engine = get_dash_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            INSERT INTO incentive_holds (manager_id, hold_date, reason, created_by)
            VALUES (:m, :d, :r, :by)
            ON CONFLICT (manager_id, hold_date)
            DO UPDATE SET reason = EXCLUDED.reason,
                          created_by = EXCLUDED.created_by,
                          released_at = NULL
        """), {"m": manager_id, "d": target, "r": reason, "by": email})
        conn.commit()


def release_hold(target: date_type, manager_id: int) -> None:
    _ensure_tables()
    engine = get_dash_engine()
    with engine.connect() as conn:
        conn.execute(text("""
            UPDATE incentive_holds SET released_at = NOW()
             WHERE manager_id = :m AND hold_date = :d AND released_at IS NULL
        """), {"m": manager_id, "d": target})
        conn.commit()


def _active_holds(target: date_type) -> dict[int, str]:
    _ensure_tables()
    engine = get_dash_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT manager_id, reason FROM incentive_holds
             WHERE hold_date = :d AND released_at IS NULL
        """), {"d": target}).fetchall()
    return {int(r.manager_id): r.reason for r in rows}


# ---------- 응답 조립 ----------
def _build_row(row, adj: dict, is_held: bool, hold_reason: str | None) -> dict:
    stops = int(adj.get("stops", {}).get("value", row.stops or 0))
    gajung = int(adj.get("gajung_qty", {}).get("value", row.gajung_qty or 0))
    mil = int(adj.get("mil_qty", {}).get("value", row.mil_qty or 0))
    collection = int(adj.get("collection_count", {}).get("value", 0))   # 수기 입력 전용
    accounts = int(adj.get("accounts", {}).get("value", stops + collection))

    product_total = gajung + mil
    prod = product_incentive(product_total)
    acct = account_incentive(accounts)
    total = prod + acct

    applied = [{"field": k, **v} for k, v in adj.items()]
    return {
        "manager_id": int(row.manager_id),
        "stops": stops, "gajung_qty": gajung, "mil_qty": mil,
        "collection_count": collection, "accounts": accounts,
        "product_total": product_total,
        "product_incentive": prod, "account_incentive": acct,
        "total_incentive": total,
        "is_held": is_held, "hold_reason": hold_reason,
        "payable_incentive": 0 if is_held else total,
        "adjustments": applied,
        "auto": {"stops": int(row.stops or 0), "gajung_qty": int(row.gajung_qty or 0),
                 "mil_qty": int(row.mil_qty or 0),
                 "accounts_distinct": int(row.accounts_distinct or 0)},
    }


def get_incentive(target: date_type, manager_id: int) -> dict:
    rows = _safe_fetch_auto(target, manager_id)
    holds = _active_holds(target)
    adjustments = _latest_adjustments(target, manager_id)
    if not rows:
        return {"date": target.isoformat(), "manager_id": manager_id,
                "stops": 0, "gajung_qty": 0, "mil_qty": 0, "collection_count": 0,
                "accounts": 0, "product_total": 0, "product_incentive": 0,
                "account_incentive": 0, "total_incentive": 0,
                "is_held": manager_id in holds, "hold_reason": holds.get(manager_id),
                "payable_incentive": 0, "adjustments": [], "auto": {}}
    r = rows[0]
    mid = int(r.manager_id)
    return {"date": target.isoformat(),
            **_build_row(r, adjustments.get(mid, {}), mid in holds, holds.get(mid))}


def get_incentive_all(target: date_type) -> dict:
    rows = _safe_fetch_auto(target, None)
    holds = _active_holds(target)
    adjustments = _latest_adjustments(target, None)
    items = [_build_row(r, adjustments.get(int(r.manager_id), {}),
                        int(r.manager_id) in holds, holds.get(int(r.manager_id)))
             for r in rows]
    return {"date": target.isoformat(), "managers": items,
            "total_incentive_sum": sum(x["total_incentive"] for x in items),
            "payable_incentive_sum": sum(x["payable_incentive"] for x in items)}
