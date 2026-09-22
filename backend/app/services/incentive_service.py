from datetime import date as date_type

from sqlalchemy import bindparam, text

from app.database import get_dash_engine, get_engine

# ── 인센티브 제품 그룹 설정 (2026-09-22 확정) ──────────────────────────
# 산식에는 GROUPS에 등록된 그룹만 합산된다.
# 석식(2) 포함 전환 = SEOKSIK_IDS 주석 해제 1줄 — 집계·산식·응답·스키마에 자동 반영.
GAJUNG_IDS = (4,)          # 가정식 단독
MIL_IDS = (23, 29)         # 밀수량 = 프레시밀 + 라이트밀
SEOKSIK_IDS: tuple = ()    # (2,)   ← 석식 포함 시 이 주석 해제

GROUPS: dict[str, tuple[int, ...]] = {
    "gajung_qty": GAJUNG_IDS,
    "mil_qty": MIL_IDS,
}
if SEOKSIK_IDS:
    GROUPS["seoksik_qty"] = SEOKSIK_IDS

# 인센티브 집계 라인업 = GROUPS 합집합 (현재 4,23,29 — 석식 제외)
# ※ deliveries·revenue API의 라인업 (2,4,23,29) 과는 별개 — 순매출에는 석식이 포함된다.
INCENTIVE_LINEUPS = tuple(sorted({p for ids in GROUPS.values() for p in ids}))

ADJUSTABLE_FIELDS = {"gajung_qty", "mil_qty", "collection_count", "stops", "accounts"}
if SEOKSIK_IDS:
    ADJUSTABLE_FIELDS.add("seoksik_qty")


# ---------- 산식 (2026-09 확정: 초과분 × 구간단가) ----------
def product_incentive(q: int) -> int:
    """제품수 인센티브 — 300 초과분에 구간단가 적용."""
    if q <= 300:
        return 0
    excess = q - 300
    rate = 50 if q <= 370 else 70 if q <= 440 else 90
    return excess * rate


def account_incentive(c: int) -> int:
    """고객사수 인센티브 — 40 초과분에 구간단가 적용 (45 이하 → 300)."""
    if c <= 40:
        return 0
    excess = c - 40
    rate = 300 if c <= 45 else 400 if c <= 50 else 500
    return excess * rate


# ---------- RDS 자동 집계 (배송지 기준 LEFT JOIN + 그룹별 수량) ----------
def _fetch_auto(target: date_type, manager_id: int | None):
    parts: list[str] = []
    group_params: dict = {}
    for i, (field, ids) in enumerate(GROUPS.items()):
        key = f"g{i}"
        parts.append(
            f"COALESCE(SUM(CASE WHEN od.product_id IN :{key} THEN od.quantity END), 0) AS {field}"
        )
        group_params[key] = list(ids)
    group_select = ",\n               ".join(parts)

    sql = f"""
        SELECT d.manager_id                          AS manager_id,
               COUNT(DISTINCT d.id)                  AS stops,
               {group_select},
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
    params: dict = {"d": target, "lineups": list(INCENTIVE_LINEUPS)}
    if manager_id is not None:
        sql += " AND d.manager_id = :mid"
        params["mid"] = manager_id
    sql += " GROUP BY d.manager_id ORDER BY d.manager_id"

    binds = [bindparam("lineups", expanding=True)] + [
        bindparam(k, expanding=True) for k in group_params
    ]
    engine = get_engine()
    with engine.connect() as conn:
        return conn.execute(text(sql).bindparams(*binds), {**params, **group_params}).fetchall()


def _safe_fetch_auto(target, manager_id):
    """터널 실패 시 1회 재시도 (Week 2 표준 패턴)."""
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
_SCHEMA_READY = False


def _ensure_tables():
    """안전망 — 스키마 소유는 마이그레이션(001). 프로세스당 1회만 실행(요청마다 DDL 금지)."""
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
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
    _SCHEMA_READY = True


def _latest_adjustments(target: date_type, manager_id: int | None) -> dict:
    """(manager, date, field) 최신 조정값 — 이력은 행으로 영구 보존."""
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
    """수기 조정 등록 — 사유 필수, 이력 적재."""
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
    """미지급 등록 — 사유 필수. 재등록 시 사유 갱신 + 재활성."""
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
    """미지급 해제 — 레코드는 유지, released_at만 기록 (기록 유지 요구)."""
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
    collection = int(adj.get("collection_count", {}).get("value", 0))   # 수기 입력 전용
    accounts = int(adj.get("accounts", {}).get("value", stops + collection))

    qty = {f: int(adj.get(f, {}).get("value", getattr(row, f, 0) or 0)) for f in GROUPS}
    product_total = sum(qty.values())
    prod = product_incentive(product_total)
    acct = account_incentive(accounts)
    total = prod + acct

    applied = [{"field": k, **v} for k, v in adj.items()]
    return {
        "manager_id": int(row.manager_id),
        "stops": stops,
        **qty,                                   # gajung_qty · mil_qty (· seoksik_qty)
        "collection_count": collection,
        "accounts": accounts,
        "product_total": product_total,
        "product_incentive": prod, "account_incentive": acct,
        "total_incentive": total,
        "is_held": is_held, "hold_reason": hold_reason,
        "payable_incentive": 0 if is_held else total,
        "adjustments": applied,
        "auto": {"stops": int(row.stops or 0),
                 **{f: int(getattr(row, f, 0) or 0) for f in GROUPS},
                 "accounts_distinct": int(row.accounts_distinct or 0)},
    }


def get_incentive(target: date_type, manager_id: int) -> dict:
    rows = _safe_fetch_auto(target, manager_id)
    holds = _active_holds(target)
    adjustments = _latest_adjustments(target, manager_id)
    if not rows:
        return {"date": target.isoformat(), "manager_id": manager_id,
                "stops": 0, "gajung_qty": 0, "mil_qty": 0, "seoksik_qty": 0,
                "collection_count": 0, "accounts": 0, "product_total": 0,
                "product_incentive": 0, "account_incentive": 0, "total_incentive": 0,
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
