from datetime import date as date_type
import re

from sqlalchemy import bindparam, text

from app.database import get_engine

# 대상 라인업 (v7 확정: 2=석식, 4=가정식, 23=프레시밀, 29=라이트밀)
LINEUP_IDS = (2, 4, 23, 29)


def normalize_delivery_hour(raw: str | None) -> str | None:
    """addresses.delivery_hour 원문에서 화면 표시용 대표 시간 1개만 추출."""
    if not raw:
        return None

    text_value = raw.strip()
    if not text_value:
        return None

    # 1) HH:MM 우선
    m = re.search(r"(\d{1,2}):(\d{2})", text_value)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return f"{hh:02d}:{mm:02d}"

    # 2) HH시MM분
    m = re.search(r"(\d{1,2})시\s*(\d{1,2})분", text_value)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return f"{hh:02d}:{mm:02d}"

    # 3) HH시
    m = re.search(r"(\d{1,2})시", text_value)
    if m:
        hh = int(m.group(1))
        if 0 <= hh <= 23:
            return f"{hh:02d}:00"

    return None


def _delivery_exists(conn, target: date_type) -> bool:
    row = conn.execute(text(
        """
        SELECT COUNT(*)
        FROM delivery
        WHERE date = :d
          AND deleted_at IS NULL
        """
    ), {"d": target}).fetchone()
    return int(row[0] or 0) > 0


def _build_response(target: date_type, rows, lineup_rows, summary_row, stop_rows, source: str) -> dict:
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

    stop_map: dict[str, dict] = {}
    for row in stop_rows:
        key = str(row.delivery_id)
        stop = stop_map.setdefault(key, {
            "delivery_id": key,
            "address_id": row.address_id,
            "address_name": row.address_name,
            "detail_address": row.detail_address,
            "latitude": float(row.latitude),
            "longitude": float(row.longitude),
            "delivery_hour_raw": row.delivery_hour,
            "delivery_time": normalize_delivery_hour(row.delivery_hour),
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

    for stop in stop_map.values():
        stop["meals"] = sum(item["qty"] for item in stop["lineups"].values())

    return {
        "date": target.isoformat(),
        "source": source,
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


def _get_actual_mode(conn, target: date_type) -> dict:
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
               SUM(CASE WHEN d.manager_id IS NULL THEN 1 ELSE 0 END) AS unassigned_stops,
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

    # 4) 지도용 stop points (실제)
    stop_rows = conn.execute(text(
        """
        SELECT d.id                            AS delivery_id,
               d.address_id                    AS address_id,
               d.manager_id                    AS manager_id,
               m.name                          AS manager_name,
               m.color                         AS manager_color,
               a.name                          AS address_name,
               a.detail_address                AS detail_address,
               a.latitude                      AS latitude,
               a.longitude                     AS longitude,
               a.delivery_hour                 AS delivery_hour,
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
                 a.name, a.detail_address, a.latitude, a.longitude, a.delivery_hour,
                 od.product_id, p.name
        ORDER BY CASE WHEN d.manager_id IS NULL THEN 1 ELSE 0 END,
                 d.manager_id,
                 d.id
        """
    ).bindparams(bindparam("lineups", expanding=True)),
      {"d": target, "lineups": list(LINEUP_IDS)}).fetchall()

    return _build_response(target, rows, lineup_rows, summary_row, stop_rows, source="delivery")


def _get_preview_mode(conn, target: date_type) -> dict:
    """마감 전 미리보기: 웹 확정(orders) + 앱 개별 선택(selected_menus, 미전환) 합산.

    - orders: 웹·어드민 주문서 (즉시 포함). 취소 규칙: deleted_at IS NULL.
    - selected_menus: 1행 = 1명이 선택한 1메뉴 → 행 수가 수량.
      * 합산 대상: order_id IS NULL(주문서 미생성 = 미전환) AND is_skipped = 0
      * 전환된 선택(order_id IS NOT NULL)은 orders에 이미 포함 → 재합산 금지
    - 배송지·고객사: orders는 o.address_id / o.account_id,
      앱 선택은 order_profiles.address_id / company_id 연결.
    - 미확정 배송지: order_profiles에 address 없음 → 별도 카운트(제외하지 않음).
    """
    # ---------- 1) 웹(orders) 매니저별 ----------
    rows = conn.execute(text(
        """
        SELECT a.manager_id,
               m.name  AS manager_name,
               m.color AS manager_color,
               COUNT(DISTINCT s.address_id)                   AS stops,
               COALESCE(SUM(od.quantity), 0)                  AS meals,
               COUNT(DISTINCT o.account_id)                   AS accounts,
               COALESCE(ROUND(SUM(od.total_amount) / 1.1), 0) AS net_revenue,
               'web'                                          AS src
        FROM orders o
        JOIN addresses a
          ON a.id = o.address_id
        JOIN `order-details` od
          ON od.order_id = o.id
         AND od.is_refund = 0
         AND od.deleted_at IS NULL
         AND od.product_id IN :lineups
        LEFT JOIN manager m
          ON m.id = a.manager_id
        WHERE o.delivery_date = :d
          AND o.deleted_at IS NULL
        GROUP BY a.manager_id, m.name, m.color

        UNION ALL

        SELECT op.address_id IS NOT NULL AND addr.manager_id AS manager_id,
               NULL AS manager_name, NULL AS manager_color,
               COUNT(DISTINCT CASE WHEN addr.id IS NOT NULL THEN op.address_id END) AS stops,
               COUNT(sm.id) AS meals,
               COUNT(DISTINCT op.company_id) AS accounts,
               0 AS net_revenue,
               'app' AS src
        FROM selected_menus sm
        JOIN schedules sc
          ON sc.id = sm.schedule_id
         AND sc.delivery_on = :d
        JOIN order_profiles op
          ON op.id = sm.order_profile_id
        LEFT JOIN addresses addr
          ON addr.id = op.address_id
        LEFT JOIN manager m
          ON m.id = addr.manager_id
        WHERE sm.order_id IS NULL
          AND sm.is_skipped = 0
          AND op.deleted_at IS NULL
        GROUP BY addr.manager_id, m.name, m.color
        """
    ).bindparams(bindparam("lineups", expanding=True)),
      {"d": target, "lineups": list(LINEUP_IDS)}).fetchall()

    # 매니저별 웹/앱 합산
    mgr_map: dict = {}
    for r in rows:
        key = r.manager_id
        e = mgr_map.setdefault(key, {
            "manager_id": key,
            "manager_name": r.manager_name,
            "manager_color": r.manager_color,
            "stops": set(), "meals": 0, "accounts": set(),
            "web_meals": 0, "app_meals": 0, "net_revenue": 0,
        })
        e["meals"] += int(r.meals or 0)
        e["net_revenue"] += int(r.net_revenue or 0)
        if r.src == "web":
            e["web_meals"] += int(r.meals or 0)
        else:
            e["app_meals"] += int(r.meals or 0)

    # ---------- 2) 지도 핀 + 배송지별 (웹 + 앱) ----------
    stop_rows = conn.execute(text(
        """
        SELECT a.id                             AS address_id,
               a.manager_id                     AS manager_id,
               m.name                           AS manager_name,
               m.color                          AS manager_color,
               a.name                           AS address_name,
               a.detail_address                 AS detail_address,
               a.latitude                       AS latitude,
               a.longitude                      AS longitude,
               a.delivery_hour                  AS delivery_hour,
               od.product_id                    AS product_id,
               p.name                           AS product_name,
               COALESCE(SUM(od.quantity), 0)    AS qty,
               COUNT(DISTINCT o.account_id)     AS accounts,
               'web'                            AS src
        FROM orders o
        JOIN addresses a
          ON a.id = o.address_id
        JOIN `order-details` od
          ON od.order_id = o.id
         AND od.is_refund = 0
         AND od.deleted_at IS NULL
         AND od.product_id IN :lineups
        LEFT JOIN products p
          ON p.id = od.product_id
        LEFT JOIN manager m
          ON m.id = a.manager_id
        WHERE o.delivery_date = :d
          AND o.deleted_at IS NULL
          AND a.latitude IS NOT NULL
          AND a.longitude IS NOT NULL
        GROUP BY a.id, a.manager_id, m.name, m.color,
                 a.name, a.detail_address, a.latitude, a.longitude, a.delivery_hour,
                 od.product_id, p.name

        UNION ALL

        SELECT op.address_id                 AS address_id,
               addr.manager_id               AS manager_id,
               m.name                        AS manager_name,
               m.color                       AS manager_color,
               addr.name                     AS address_name,
               addr.detail_address           AS detail_address,
               addr.latitude                 AS latitude,
               addr.longitude                AS longitude,
               addr.delivery_hour            AS delivery_hour,
               smp.product_id                AS product_id,
               pp.name                       AS product_name,
               COUNT(sm.id)                  AS qty,
               COUNT(DISTINCT op.company_id) AS accounts,
               'app'                         AS src
        FROM selected_menus sm
        JOIN schedules sc
          ON sc.id = sm.schedule_id
         AND sc.delivery_on = :d
        JOIN scheduled_menus smp
          ON smp.id = sm.scheduled_menu_id
        JOIN order_profiles op
          ON op.id = sm.order_profile_id
        JOIN addresses addr
          ON addr.id = op.address_id
        LEFT JOIN products pp
          ON pp.id = smp.product_id
        LEFT JOIN manager m
          ON m.id = addr.manager_id
        WHERE sm.order_id IS NULL
          AND sm.is_skipped = 0
          AND op.deleted_at IS NULL
          AND addr.latitude IS NOT NULL
          AND addr.longitude IS NOT NULL
          AND smp.product_id IN :lineups
        GROUP BY addr.id, addr.manager_id, m.name, m.color,
                 addr.name, addr.detail_address, addr.latitude, addr.longitude, addr.delivery_hour,
                 smp.product_id, pp.name
        """
    ).bindparams(bindparam("lineups", expanding=True)),
      {"d": target, "lineups": list(LINEUP_IDS)}).fetchall()

    # 배송지별 병합: 웹+앱 수량 합산, 라인업 병합
    stop_map: dict = {}
    web_qty_total = 0
    app_qty_total = 0
    unconfirmed_stops = 0
    unconfirmed_qty = 0

    for r in stop_rows:
        key = str(r.address_id)
        if key not in stop_map:
            stop_map[key] = {
                "delivery_id": None,
                "address_id": r.address_id,
                "address_name": r.address_name,
                "detail_address": r.detail_address,
                "latitude": float(r.latitude) if r.latitude is not None else None,
                "longitude": float(r.longitude) if r.longitude is not None else None,
                "delivery_hour_raw": r.delivery_hour,
                "delivery_time": _normalize_delivery_hour(r.delivery_hour),
                "manager_id": r.manager_id,
                "manager_name": r.manager_name,
                "manager_color": r.manager_color,
                "accounts": int(r.accounts or 0),
                "meals": 0,
                "lineups": {},
            }
        stop = stop_map[key]
        qty = int(r.qty or 0)
        stop["meals"] += qty
        lu = stop["lineups"].setdefault(str(r.product_id), {
            "name": r.product_name or str(r.product_id), "qty": 0,
        })
        lu["qty"] += qty

        if r.src == "web":
            web_qty_total += qty
        else:
            app_qty_total += qty

    # ---------- 3) 미확정 배송지 (앱 선택 + order_profiles에 주소 없음) ----------
    unconf = conn.execute(text(
        """
        SELECT COUNT(DISTINCT sm.id)        AS cnt,
               COUNT(sm.id)                 AS qty
        FROM selected_menus sm
        JOIN schedules sc
          ON sc.id = sm.schedule_id
         AND sc.delivery_on = :d
        JOIN order_profiles op
          ON op.id = sm.order_profile_id
        WHERE sm.order_id IS NULL
          AND sm.is_skipped = 0
          AND op.deleted_at IS NULL
          AND (op.address_id IS NULL)
        """
    ), {"d": target}).fetchone()
    unconfirmed_stops = int(unconf[0] or 0)
    unconfirmed_qty = int(unconf[1] or 0)

    # ---------- 4) 전체 요약 (매니저 맵에서 합산) ----------
    all_stops = set()
    all_accounts = set()
    for k, e in mgr_map.items():
        for sk in stop_map.values():
            if sk["manager_id"] == k:
                all_stops.add(str(sk["address_id"]))
    for sk in stop_map.values():
        pass

    # 고객사 수는 웹/앱 별도 쿼리 결과의 DISTINCT 합을 재집계 (단순 합산은 중복 위험)
    acc_row = conn.execute(text(
        """
        SELECT COUNT(DISTINCT acc) AS accounts FROM (
            SELECT o.account_id AS acc
            FROM orders o
            WHERE o.delivery_date = :d AND o.deleted_at IS NULL
            UNION
            SELECT op.company_id AS acc
            FROM selected_menus sm
            JOIN schedules sc ON sc.id = sm.schedule_id AND sc.delivery_on = :d
            JOIN order_profiles op ON op.id = sm.order_profile_id
            WHERE sm.order_id IS NULL AND sm.is_skipped = 0 AND op.deleted_at IS NULL
              AND op.company_id IS NOT NULL
        ) t
        """
    ), {"d": target}).fetchone()

    stops_total = len(stop_map)
    meals_total = web_qty_total + app_qty_total

    managers = []
    for k, e in mgr_map.items():
        # 매니저별 stops는 stop_map 기준으로 재계산 (중복 방지)
        own = [sk for sk in stop_map.values() if sk["manager_id"] == k]
        managers.append({
            "manager_id": e["manager_id"],
            "manager_name": e["manager_name"],
            "manager_color": e["manager_color"],
            "stops": len(own),
            "meals": sum(sk["meals"] for sk in own),
            "accounts": max((sk["accounts"] for sk in own), default=0),
            "net_revenue": e["net_revenue"],
            "lineups": {},
        })
    managers.sort(key=lambda x: -(x["stops"]))

    # 라인업별 매니저 집계 (기존 구조 유지: lineups)
    lineup_rows = conn.execute(text(
        """
        SELECT a.manager_id AS manager_id,
               od.product_id AS product_id,
               p.name        AS product_name,
               COALESCE(SUM(od.quantity), 0) AS qty,
               COALESCE(ROUND(SUM(od.total_amount) / 1.1), 0) AS amount
        FROM orders o
        JOIN addresses a ON a.id = o.address_id
        JOIN `order-details` od
          ON od.order_id = o.id
         AND od.is_refund = 0
         AND od.deleted_at IS NULL
         AND od.product_id IN :lineups
        LEFT JOIN products p ON p.id = od.product_id
        WHERE o.delivery_date = :d AND o.deleted_at IS NULL
        GROUP BY a.manager_id, od.product_id, p.name
        """
    ).bindparams(bindparam("lineups", expanding=True)),
      {"d": target, "lineups": list(LINEUP_IDS)}).fetchall()

    return _build_response_preview(
        target, managers, lineup_rows, stops_total, meals_total,
        int(acc_row[0] or 0), unconfirmed_stops, unconfirmed_qty,
        web_qty_total, app_qty_total, stop_map.values(),
    )


def _build_response_preview(target, managers, lineup_rows, stops_total, meals_total,
                            accounts_total, unconfirmed_stops, unconfirmed_qty,
                            web_qty, app_qty, stops):
    stops_list = []
    for sk in stops:
        s2 = dict(sk)
        s2["meals"] = sum(v["qty"] for v in sk["lineups"].values())
        stops_list.append(s2)

    return {
        "date": target.isoformat(),
        "source": "orders_with_app",
        "summary": {
            "stops": stops_total,
            "meals": meals_total,
            "accounts": accounts_total,
            "completed_stops": 0,
            "unassigned_stops": sum(1 for s2 in stops_list if s2["manager_id"] is None),
            "web_qty": web_qty,
            "app_qty": app_qty,
            "total_qty": meals_total,
            "unconfirmed_stops": unconfirmed_stops,
            "unconfirmed_qty": unconfirmed_qty,
        },
        "managers": managers,
        "unassigned": {"stops": sum(1 for s2 in stops_list if s2["manager_id"] is None)},
        "stops": stops_list,
    }


def get_delivery_day(target: date_type) -> dict:
    """delivery 있으면 실제, 없으면 orders+addresses 기반 예상 배송현황."""
    engine = get_engine()
    with engine.connect() as conn:
        if _delivery_exists(conn, target):
            return _get_actual_mode(conn, target)
        return _get_preview_mode(conn, target)
