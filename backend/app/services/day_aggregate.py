"""S0-P4.6 하루 집계 단일 원천.

상단 카드(status_service) · 지도/매니저 표(delivery_service) · 미리보기 경로(routes_service)가
모두 build_day() 결과 하나만 사용한다. 운영 DB에는 SELECT만 실행한다.

[확정 규칙 - 2026-09-30 검증]
- 라인업: 중식 4(가정식)·23(프레시밀)·29(라이트밀), 석식 2
- 주문(웹·어드민·앱전환): orders.deleted_at IS NULL + order-details.deleted_at IS NULL
  · is_refund=0 = 판매, is_refund=1 = 환불(금액 양수 기록 → 차감)
  · 매출은 VAT 제외(÷1.1). 순매출 = 총매출 - 환불
- 앱 미전환 선택: selected_menus(order_id IS NULL, is_skipped=0), 1행 = 1식
  · order_profiles.address_id = addresses.record_id
  · order_profiles.company_id = accounts.record_id
  · scheduled_menus.product_id = products.record_id
  · 예상 단가 = account_product_policy.price(0=무료) 없으면 products.price
- 마감: schedules.order_completed_at(UTC) 최댓값 → KST. 없으면 전날 14:30 KST
- 모드
  · delivery       : delivery 행 존재 → delivery 행 = 배송지
  · preview_open   : delivery 없음 + 마감 전 → 주문 + 앱 미전환(예상)
  · preview_closed : delivery 없음 + 마감 후 → 주문만, 남은 미전환은 경고
"""
from __future__ import annotations

import os
import re
from datetime import date as date_type, datetime, time, timedelta, timezone

from sqlalchemy import bindparam, text

KST = timezone(timedelta(hours=9))

LUNCH_PRODUCT_IDS = (4, 23, 29)
DINNER_PRODUCT_IDS = (2,)
LINEUP_IDS = LUNCH_PRODUCT_IDS + DINNER_PRODUCT_IDS
LINEUP_ORDER = (4, 23, 29, 2)
DEFAULT_CUTOFF_TIME = time(14, 30)

# 앱(배송 처리)이 쓰는 시각 컬럼은 UTC로 저장된다 (DB 서버 시간대 KST와 무관).
# 앱 저장 방식이 바뀌면 .env에 OPS_NAIVE_TZ=KST
OPS_NAIVE_TZ = KST if os.environ.get("OPS_NAIVE_TZ", "UTC").upper() == "KST" else timezone.utc


def to_kst(raw) -> datetime | None:
    """앱 기록 시각(UTC, 시간대 없음) → KST(aware). API에 +09:00이 붙어 나간다."""
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if raw.tzinfo is None:
        raw = raw.replace(tzinfo=OPS_NAIVE_TZ)
    return raw.astimezone(KST)

MODE_DELIVERY = "delivery"
MODE_PREVIEW_OPEN = "preview_open"
MODE_PREVIEW_CLOSED = "preview_closed"

SOURCE_BY_MODE = {
    MODE_DELIVERY: "delivery",
    MODE_PREVIEW_OPEN: "orders_with_app",
    MODE_PREVIEW_CLOSED: "orders",
}

_SRC_FIELD = {
    "web": "web_qty",
    "admin": "admin_qty",
    "app": "app_converted_qty",
    "app_pending": "app_pending_qty",
}


# =====================================================================
# 순수 함수 (DB 없음 → CI 단위 테스트 대상)
# =====================================================================
def meal_of(product_id) -> str:
    return "dinner" if int(product_id) in DINNER_PRODUCT_IDS else "lunch"


def ex_vat(amount) -> int:
    """VAT 포함 → VAT 제외(÷1.1, 원 단위 반올림). 정수 연산으로 오차 없음."""
    a = int(amount or 0)
    if a < 0:
        return -ex_vat(-a)
    return (a * 20 + 11) // 22


def normalize_delivery_hour(raw: str | None) -> str | None:
    """addresses.delivery_hour 원문에서 대표 시간 1개만 추출."""
    if not raw:
        return None
    v = raw.strip()
    if not v:
        return None
    m = re.search(r"(\d{1,2}):(\d{2})", v)
    if m and 0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2)) <= 59:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
    m = re.search(r"(\d{1,2})시\s*(\d{1,2})분", v)
    if m and 0 <= int(m.group(1)) <= 23 and 0 <= int(m.group(2)) <= 59:
        return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
    m = re.search(r"(\d{1,2})시", v)
    if m and 0 <= int(m.group(1)) <= 23:
        return f"{int(m.group(1)):02d}:00"
    return None


def cutoff_from_schedule(raw, target: date_type) -> tuple[datetime, str]:
    """schedules.order_completed_at(앱 기록 UTC) → KST. 없으면 전날 14:30 KST."""
    v = to_kst(raw)
    if v is not None:
        return v, "schedule"
    prev = target - timedelta(days=1)
    return datetime.combine(prev, DEFAULT_CUTOFF_TIME, tzinfo=KST), "default"


def decide_mode(has_delivery: bool, now: datetime, cutoff_at: datetime) -> str:
    if has_delivery:
        return MODE_DELIVERY
    return MODE_PREVIEW_OPEN if now < cutoff_at else MODE_PREVIEW_CLOSED


def _has_coord(lat, lng) -> bool:
    # 0 좌표도 미입력으로 본다 (국내 배송지에 0 좌표는 존재 불가)
    return lat is not None and lng is not None and float(lat) != 0 and float(lng) != 0


def prepare_lines(raw_lines: list[dict]) -> list[dict]:
    """원시 행 → 정규화 + VAT 제외 금액 계산. 수량·환불이 모두 0인 행은 버린다."""
    out = []
    for r in raw_lines:
        qty = int(r.get("qty") or 0)
        refund_qty = int(r.get("refund_qty") or 0)
        gross = int(r.get("gross") or 0)
        refund = int(r.get("refund") or 0)
        if qty <= 0 and refund_qty <= 0 and refund <= 0:
            continue
        src = r.get("src") or "web"
        if src not in _SRC_FIELD:
            src = "web"
        aid = r.get("address_id")
        out.append({
            "src": src,
            "address_id": int(aid) if aid is not None else None,
            "account_key": r.get("account_key"),
            "product_id": int(r["product_id"]),
            "product_name": r.get("product_name"),
            "qty": qty,
            "refund_qty": refund_qty,
            # 행(그룹) 단위로 반올림 → 모든 화면이 같은 정수를 더하므로 합계가 항상 일치
            "gross_ex": ex_vat(gross),
            "refund_ex": ex_vat(refund),
            "estimated": bool(r.get("estimated")),
        })
    return out


def _bucket() -> dict:
    return {
        "meals": 0, "lunch_meals": 0, "dinner_meals": 0,
        "web_qty": 0, "admin_qty": 0, "app_converted_qty": 0, "app_pending_qty": 0,
        "refund_qty": 0, "gross_revenue": 0, "refund_amount": 0, "estimated_revenue": 0,
        "internal_meals": 0, "internal_gross": 0, "internal_refund": 0,
    }


def _add_line(b: dict, ln: dict) -> None:
    """수량은 항상 포함(일감·실적). 직원식 주문의 금액은 매출이 아니라 internal_*로만 보낸다."""
    q = ln["qty"]
    b["meals"] += q
    b["dinner_meals" if meal_of(ln["product_id"]) == "dinner" else "lunch_meals"] += q
    b[_SRC_FIELD[ln["src"]]] += q
    b["refund_qty"] += ln["refund_qty"]
    if ln.get("internal"):
        b["internal_meals"] += q
        b["internal_gross"] += ln["gross_ex"]
        b["internal_refund"] += ln["refund_ex"]
        return
    b["gross_revenue"] += ln["gross_ex"]
    b["refund_amount"] += ln["refund_ex"]
    if ln["estimated"]:
        b["estimated_revenue"] += ln["gross_ex"]


def _merge(dst: dict, src: dict) -> None:
    for k in dst:
        dst[k] += src[k]


def _finish(b: dict) -> dict:
    out = dict(b)
    out["app_qty"] = b["app_converted_qty"] + b["app_pending_qty"]
    out["net_revenue"] = b["gross_revenue"] - b["refund_amount"]
    out["internal_net"] = b["internal_gross"] - b["internal_refund"]
    return out


def _merge_lineups(dst: dict, src: dict) -> None:
    for pid, v in src.items():
        d = dst.setdefault(pid, {"name": v["name"], "qty": 0, "amount": 0, "internal_qty": 0})
        d["qty"] += v["qty"]
        d["amount"] += v["amount"]
        d["internal_qty"] += v.get("internal_qty", 0)


# =====================================================================
# 직원식 대상 (현재: .env, 기본 비어 있음 → 푸시 3.1에서 설정 페이지/DB로 이전)
# =====================================================================
def _parse_ids(env_name: str) -> set:
    raw = os.environ.get(env_name, "")
    return {int(x) for x in raw.split(",") if x.strip().isdigit()}


def internal_targets() -> dict:
    """직원식 대상 = 설정 페이지(dash_db) ∪ .env(비상용). 비어 있으면 모든 주문이 일반 매출."""
    out = {
        "address_ids": _parse_ids("INTERNAL_ADDRESS_IDS"),
        "account_ids": _parse_ids("INTERNAL_ACCOUNT_IDS"),
    }
    try:
        from app.services import internal_target_service as its   # 지연 import (순환 방지)
        db = its.active_targets()
        out["address_ids"] |= set(db.get("address_ids") or ())
        out["account_ids"] |= set(db.get("account_ids") or ())
    except Exception:  # noqa: BLE001 - 설정 조회 실패가 집계를 막지 않게
        pass
    return out


def mark_internal(stop_infos: list[dict], lines: list[dict], targets: dict) -> None:
    """배송지·주문 행에 직원식 표시만 붙인다. 목록에서 빼지 않는다(일감·실적 유지)."""
    addr = set(targets.get("address_ids") or ())
    acc = set(targets.get("account_ids") or ())
    for s in stop_infos:
        s["is_internal"] = s.get("address_id") in addr or s.get("account_id") in acc
    int_addr = {s["address_id"] for s in stop_infos
                if s["is_internal"] and s.get("address_id") is not None} | addr
    for ln in lines:
        ln["internal"] = ln["address_id"] in int_addr or ln["account_key"] in acc


def internal_view(agg: dict, enabled: bool = True) -> dict:
    """직원식 별도 표시용 (수량·금액). 이미 합계 안에 들어 있는 값을 따로 보여주는 것."""
    t = agg["totals"]
    by_lu = {
        k: {"name": v["name"], "meal": v["meal"], "qty": v["internal_qty"], "net_revenue": v["internal_net"]}
        for k, v in agg["by_lineup"].items() if v["internal_qty"] or v["internal_net"]
    }
    return {
        "enabled": enabled,
        "stops": t["internal_stops"],
        "meals": t["internal_meals"],
        "gross_revenue": t["internal_gross"],
        "refund_amount": t["internal_refund"],
        "net_revenue": t["internal_net"],
        "by_lineup": by_lu,
        "places": [{
            "address_id": s["address_id"],
            "address_name": s["address_name"],
            "manager_name": s["manager_name"],
            "meals": s["internal_meals"],
            "net_revenue": s["internal_net"],
            "delivered": s["delivered_at"] is not None,
        } for s in agg["stops"] if s["is_internal"] or s["internal_meals"]],
    }


def assemble(target: date_type, mode: str, cutoff_at: datetime, cutoff_source: str,
             stop_infos: list[dict], lines: list[dict], warnings: dict | None = None) -> dict:
    """정규화된 배송지·행으로 모든 화면용 숫자를 만든다 (순수 함수)."""
    warnings = dict(warnings or {})

    stops: dict = {}
    addr_to_key: dict = {}
    for info in stop_infos:
        key = info["key"]
        stops[key] = {"info": info, "b": _bucket(), "accounts": set(), "lineups": {}}
        if info.get("address_id") is not None:
            # 같은 주소에 delivery 행이 여러 개면 첫 행에만 주문을 붙인다 (이중 합산 방지)
            addr_to_key.setdefault(int(info["address_id"]), key)

    total = _bucket()
    all_accounts: set = set()
    by_lineup: dict = {}
    unplaced_lines = 0
    unplaced_qty = 0

    for ln in lines:
        key = addr_to_key.get(ln["address_id"])
        if key is None:
            unplaced_lines += 1
            unplaced_qty += ln["qty"]
            continue
        s = stops[key]
        _add_line(s["b"], ln)
        _add_line(total, ln)
        if ln["qty"] > 0 and ln["account_key"] is not None:
            s["accounts"].add(ln["account_key"])
            all_accounts.add(ln["account_key"])

        pid = str(ln["product_id"])
        name = ln["product_name"] or pid
        net = ln["gross_ex"] - ln["refund_ex"]
        is_int = bool(ln.get("internal"))

        lu = s["lineups"].setdefault(pid, {"name": name, "qty": 0, "amount": 0, "internal_qty": 0})
        lu["qty"] += ln["qty"]
        if is_int:
            lu["internal_qty"] += ln["qty"]
        else:
            lu["amount"] += net

        bl = by_lineup.setdefault(pid, {
            "name": name, "meal": meal_of(ln["product_id"]), "qty": 0, "refund_qty": 0,
            "gross_revenue": 0, "refund_amount": 0, "net_revenue": 0,
            "internal_qty": 0, "internal_net": 0,
        })
        bl["qty"] += ln["qty"]
        bl["refund_qty"] += ln["refund_qty"]
        if is_int:
            bl["internal_qty"] += ln["qty"]
            bl["internal_net"] += net
        else:
            bl["gross_revenue"] += ln["gross_ex"]
            bl["refund_amount"] += ln["refund_ex"]
            bl["net_revenue"] += net

    # ---- 배송지 출력 ----
    stops_out = []
    for key, s in stops.items():
        info = s["info"]
        lat, lng = info.get("latitude"), info.get("longitude")
        has_coord = _has_coord(lat, lng)
        stop = {
            "delivery_id": info["delivery_id"],
            "route_item_id": info["route_item_id"],
            "address_id": info.get("address_id"),
            "address_name": info.get("address_name"),
            "detail_address": info.get("detail_address"),
            "latitude": float(lat) if has_coord else None,
            "longitude": float(lng) if has_coord else None,
            "has_coord": has_coord,
            "delivery_hour_raw": info.get("delivery_hour"),
            "delivery_time": normalize_delivery_hour(info.get("delivery_hour")),
            "manager_id": info.get("manager_id"),
            "manager_name": info.get("manager_name"),
            "manager_color": info.get("manager_color"),
            "delivered_at": info.get("delivered_at"),
            "is_internal": bool(info.get("is_internal")),
            "accounts": len(s["accounts"]),
            "lineups": s["lineups"],
            "_key": key,
        }
        stop.update(_finish(s["b"]))
        stops_out.append(stop)

    stops_out.sort(key=lambda x: (x["manager_id"] is None, x["manager_id"] or 0, str(x["delivery_id"])))

    # ---- 매니저 출력 (배송지 묶음을 그대로 합산) ----
    mgrs: dict = {}
    for st in stops_out:
        s = stops[st["_key"]]
        mk = st["manager_id"]
        m = mgrs.setdefault(mk, {
            "manager_id": mk, "manager_name": st["manager_name"], "color": st["manager_color"],
            "b": _bucket(), "accounts": set(), "stops": 0, "internal_stops": 0, "lineups": {},
        })
        m["stops"] += 1
        m["internal_stops"] += 1 if st["is_internal"] else 0
        _merge(m["b"], s["b"])
        m["accounts"] |= s["accounts"]
        _merge_lineups(m["lineups"], s["lineups"])

    managers = []
    for m in mgrs.values():
        row = {
            "manager_id": m["manager_id"],
            "manager_name": m["manager_name"],
            "color": m["color"],
            "manager_color": m["color"],
            "stops": m["stops"],
            "internal_stops": m["internal_stops"],
            "accounts": len(m["accounts"]),
            "lineups": m["lineups"],
        }
        row.update(_finish(m["b"]))
        managers.append(row)
    managers.sort(key=lambda x: (-x["stops"], x["manager_id"] is None, x["manager_id"] or 0))

    for st in stops_out:
        st.pop("_key", None)

    totals = _finish(total)
    no_coord = sum(1 for st in stops_out if not st["has_coord"])
    totals.update({
        "stops": len(stops_out),
        "accounts": len(all_accounts),
        "completed_stops": sum(1 for st in stops_out if st["delivered_at"] is not None),
        "unassigned_stops": sum(1 for st in stops_out if st["manager_id"] is None),
        "no_coord_stops": no_coord,
        "internal_stops": sum(1 for st in stops_out if st["is_internal"]),
    })
    warnings.update({
        "unplaced_lines": unplaced_lines,
        "unplaced_qty": unplaced_qty,
        "no_coord_stops": no_coord,
    })

    ordered_lineup = {k: by_lineup[k] for k in [str(p) for p in LINEUP_ORDER] if k in by_lineup}

    return {
        "date": target.isoformat(),
        "mode": mode,
        "source": SOURCE_BY_MODE[mode],
        "estimated": mode != MODE_DELIVERY,
        "cutoff_at": cutoff_at.isoformat(),
        "cutoff_source": cutoff_source,
        "totals": totals,
        "by_lineup": ordered_lineup,
        "managers": managers,
        "stops": stops_out,
        "warnings": warnings,
    }


# =====================================================================
# 화면별 변환 (순수 함수) — 같은 agg에서만 만든다
# =====================================================================
def status_view(agg: dict, now: datetime) -> dict:
    target = date_type.fromisoformat(agg["date"])
    today = now.astimezone(KST).date()
    cutoff_at = datetime.fromisoformat(agg["cutoff_at"])
    t = agg["totals"]
    has_delivery = agg["mode"] == MODE_DELIVERY
    delivery_total = t["stops"] if has_delivery else 0
    completed = t["completed_stops"] if has_delivery else 0
    has_orders = t["stops"] > 0

    if now < cutoff_at:
        state = "PREVIEW"
    elif delivery_total == 0 and not has_orders:
        state = "NONE"
    elif target < today:
        state = "RESULT"
    elif target == today:
        if delivery_total > 0 and completed >= delivery_total:
            state = "RESULT"
        elif delivery_total > 0:
            state = "LIVE"
        elif has_orders:
            state = "PREVIEW"
        else:
            state = "NONE"
    else:
        state = "PREVIEW"

    show_total = t["stops"] if (has_delivery or state == "PREVIEW") else 0
    progress = {"completed": completed, "total": show_total, "unassigned": t["unassigned_stops"]}

    estimate = None
    if state == "PREVIEW":
        estimate = {
            "total": t["stops"],
            "estimated_meals": t["meals"],
            "estimated_accounts": t["accounts"],
            "estimated_net_revenue": t["net_revenue"],
            "estimated_gross_revenue": t["gross_revenue"],
            "estimated_refund_amount": t["refund_amount"],
            "lunch_meals": t["lunch_meals"],
            "dinner_meals": t["dinner_meals"],
            "web_qty": t["web_qty"],
            "admin_qty": t["admin_qty"],
            "app_qty": t["app_qty"],
            "app_converted_qty": t["app_converted_qty"],
            "app_pending_qty": t["app_pending_qty"],
            "internal_meals": t["internal_meals"],
            "internal_net_revenue": t["internal_net"],
        }

    return {
        "date": agg["date"],
        "state": state,
        "incomplete": (delivery_total - completed) if state == "RESULT" else 0,
        "cutoff_at": agg["cutoff_at"],
        "now": now.isoformat(),
        "progress": progress,
        "estimate": estimate,
        "source": agg["source"],
        "mode": agg["mode"],
        "cutoff_source": agg["cutoff_source"],
        "estimated": agg["estimated"],
        "totals": t,
        "warnings": agg["warnings"],
        "internal": agg.get("internal"),
    }


def delivery_view(agg: dict) -> dict:
    t = agg["totals"]
    w = agg["warnings"]
    summary = dict(t)
    summary["total_qty"] = t["meals"]                          # 하위 호환
    summary["unconfirmed_stops"] = w.get("unplaced_lines", 0)  # 하위 호환
    summary["unconfirmed_qty"] = w.get("unplaced_qty", 0)
    return {
        "date": agg["date"],
        "source": agg["source"],
        "mode": agg["mode"],
        "estimated": agg["estimated"],
        "cutoff_at": agg["cutoff_at"],
        "summary": summary,
        "managers": agg["managers"],
        "unassigned": {"stops": t["unassigned_stops"]},
        "stops": agg["stops"],
        "by_lineup": agg["by_lineup"],
        "warnings": w,
        "internal": agg.get("internal") or {},
    }


# =====================================================================
# DB 조회 (SELECT만)
# =====================================================================
SQL_CUTOFF = "SELECT MAX(order_completed_at) FROM schedules WHERE delivery_on = :d"

SQL_DELIVERY_STOPS = """
SELECT d.id AS delivery_id, d.address_id, d.manager_id, d.delivered_at, a.account_id,
       m.name AS manager_name, m.color AS manager_color,
       a.name AS address_name, a.detail_address, a.latitude, a.longitude, a.delivery_hour
FROM delivery d
LEFT JOIN addresses a ON a.id = d.address_id
LEFT JOIN manager m ON m.id = d.manager_id
WHERE d.date = :d AND d.deleted_at IS NULL
ORDER BY d.id
"""

SQL_ADDRESS_STOPS = """
SELECT a.id AS address_id, a.account_id, a.manager_id, m.name AS manager_name, m.color AS manager_color,
       a.name AS address_name, a.detail_address, a.latitude, a.longitude, a.delivery_hour
FROM addresses a
LEFT JOIN manager m ON m.id = a.manager_id
WHERE a.id IN :ids
"""

SQL_ORDER_LINES = """
SELECT o.address_id, o.account_id, o.source, od.product_id, p.name AS product_name,
       SUM(CASE WHEN od.is_refund = 0 THEN od.quantity     ELSE 0 END) AS qty,
       SUM(CASE WHEN od.is_refund = 0 THEN od.total_amount ELSE 0 END) AS gross,
       SUM(CASE WHEN od.is_refund = 1 THEN od.quantity     ELSE 0 END) AS refund_qty,
       SUM(CASE WHEN od.is_refund = 1 THEN od.total_amount ELSE 0 END) AS refund
FROM orders o
JOIN `order-details` od
  ON od.order_id = o.id
 AND od.deleted_at IS NULL
 AND od.product_id IN :lineups
LEFT JOIN products p ON p.id = od.product_id
WHERE o.delivery_date = :d
  AND o.deleted_at IS NULL
GROUP BY o.address_id, o.account_id, o.source, od.product_id, p.name
"""

SQL_APP_PENDING = """
SELECT a.id AS address_id, acc.id AS account_id, op.company_id AS company_rec,
       p.id AS product_id, p.name AS product_name, p.price AS base_price,
       app.price AS policy_price, COALESCE(app.block, 0) AS blocked,
       COUNT(sm.id) AS qty
FROM selected_menus sm
JOIN schedules sc ON sc.id = sm.schedule_id AND sc.delivery_on = :d
JOIN scheduled_menus smp ON smp.id = sm.scheduled_menu_id
JOIN order_profiles op ON op.id = sm.order_profile_id
LEFT JOIN addresses a ON a.record_id = op.address_id
LEFT JOIN accounts acc ON acc.record_id = op.company_id
LEFT JOIN products p ON p.record_id = smp.product_id
LEFT JOIN account_product_policy app ON app.account_id = acc.id AND app.product_id = p.id
WHERE sm.order_id IS NULL
  AND sm.is_skipped = 0
  AND op.deleted_at IS NULL
GROUP BY a.id, acc.id, op.company_id, p.id, p.name, p.price, app.price, app.block
"""

SQL_INSUFFICIENT = "SELECT COUNT(*) FROM insufficient_selected_menus WHERE delivery_on = :d"

SQL_CANCELLED = """
SELECT o.id AS order_id, o.source, o.address_id,
       COALESCE(SUM(CASE WHEN od.is_refund = 0 AND od.product_id IN :lineups
                         THEN od.quantity ELSE 0 END), 0) AS qty
FROM orders o
LEFT JOIN `order-details` od ON od.order_id = o.id
WHERE o.delivery_date = :d
  AND o.deleted_at IS NOT NULL
GROUP BY o.id, o.source, o.address_id
"""


def summarize_cancelled(rows, live_address_ids: set) -> dict:
    """삭제된 주문(=취소) 요약. 라인업 수량이 없는 삭제 주문은 제외.
    cancelled_stops = 취소로 남은 주문이 하나도 없게 된 배송지 수."""
    by_source: dict = {}
    lost: set = set()
    orders = qty = 0
    live = {str(a) for a in live_address_ids}
    for r in rows:
        q = int(r.get("qty") or 0)
        if q <= 0:
            continue
        src = r.get("source") or "web"
        b = by_source.setdefault(src, {"orders": 0, "qty": 0})
        b["orders"] += 1
        b["qty"] += q
        orders += 1
        qty += q
        aid = r.get("address_id")
        if aid is not None and str(aid) not in live:
            lost.add(str(aid))
    return {
        "cancelled_orders": orders,
        "cancelled_qty": qty,
        "cancelled_stops": len(lost),
        "cancelled_by_source": by_source,
    }


def fetch_cancelled(conn, target: date_type) -> list[dict]:
    rows = conn.execute(
        text(SQL_CANCELLED).bindparams(bindparam("lineups", expanding=True)),
        {"d": target, "lineups": list(LINEUP_IDS)},
    ).mappings().all()
    return [dict(r) for r in rows]


def resolve_cutoff(conn, target: date_type) -> tuple[datetime, str]:
    row = conn.execute(text(SQL_CUTOFF), {"d": target}).fetchone()
    return cutoff_from_schedule(row[0] if row else None, target)


def delivery_row_to_info(r) -> dict:
    """delivery 행 → 배송지 정보. delivery.id는 UUID 문자열이므로 형 변환하지 않는다."""
    return {
        "key": f"d{r['delivery_id']}",
        "delivery_id": str(r["delivery_id"]),
        "route_item_id": r["delivery_id"],
        "address_id": r["address_id"],
        "account_id": r.get("account_id"),        
        "address_name": r["address_name"],
        "detail_address": r["detail_address"],
        "latitude": r["latitude"],
        "longitude": r["longitude"],
        "delivery_hour": r["delivery_hour"],
        "manager_id": r["manager_id"],
        "manager_name": r["manager_name"],
        "manager_color": r["manager_color"],
        "delivered_at": to_kst(r["delivered_at"]),
    }


def fetch_delivery_stops(conn, target: date_type) -> list[dict]:
    rows = conn.execute(text(SQL_DELIVERY_STOPS), {"d": target}).mappings().all()
    return [delivery_row_to_info(r) for r in rows]


def fetch_address_stops(conn, address_ids: list[int]) -> list[dict]:
    if not address_ids:
        return []
    rows = conn.execute(
        text(SQL_ADDRESS_STOPS).bindparams(bindparam("ids", expanding=True)),
        {"ids": list(address_ids)},
    ).mappings().all()
    return [{
        "key": f"a{r['address_id']}",
        "delivery_id": f"preview-{r['address_id']}",
        "route_item_id": int(r["address_id"]),
        "address_id": int(r["address_id"]),
        "account_id": r["account_id"],        
        "address_name": r["address_name"],
        "detail_address": r["detail_address"],
        "latitude": r["latitude"],
        "longitude": r["longitude"],
        "delivery_hour": r["delivery_hour"],
        "manager_id": r["manager_id"],
        "manager_name": r["manager_name"],
        "manager_color": r["manager_color"],
        "delivered_at": None,
    } for r in sorted(rows, key=lambda x: x["address_id"])]


def fetch_order_lines(conn, target: date_type) -> list[dict]:
    rows = conn.execute(
        text(SQL_ORDER_LINES).bindparams(bindparam("lineups", expanding=True)),
        {"d": target, "lineups": list(LINEUP_IDS)},
    ).mappings().all()
    out = []
    for r in rows:
        src = r["source"] if r["source"] in ("web", "admin", "app") else "web"
        out.append({
            "src": src,
            "address_id": r["address_id"],
            "account_key": int(r["account_id"]) if r["account_id"] is not None else None,
            "product_id": r["product_id"],
            "product_name": r["product_name"],
            "qty": r["qty"], "gross": r["gross"],
            "refund_qty": r["refund_qty"], "refund": r["refund"],
            "estimated": False,
        })
    return out


def fetch_app_pending(conn, target: date_type) -> tuple[list[dict], dict]:
    rows = conn.execute(text(SQL_APP_PENDING), {"d": target}).mappings().all()
    issues = {
        "app_pending_total_qty": 0,
        "app_unmatched_address_qty": 0,
        "app_unmapped_product_qty": 0,
        "app_blocked_qty": 0,
    }
    lines = []
    for r in rows:
        qty = int(r["qty"] or 0)
        issues["app_pending_total_qty"] += qty
        pid = r["product_id"]
        if pid is None or int(pid) not in LINEUP_IDS:
            issues["app_unmapped_product_qty"] += qty
            continue
        if r["address_id"] is None:
            issues["app_unmatched_address_qty"] += qty
            continue
        if int(r["blocked"] or 0) == 1:
            issues["app_blocked_qty"] += qty
            continue
        unit = r["policy_price"] if r["policy_price"] is not None else (r["base_price"] or 0)
        account_key = int(r["account_id"]) if r["account_id"] is not None else f"rec:{r['company_rec']}"
        lines.append({
            "src": "app_pending",
            "address_id": r["address_id"],
            "account_key": account_key,
            "product_id": pid,
            "product_name": r["product_name"],
            "qty": qty,
            "gross": int(unit) * qty,
            "refund_qty": 0, "refund": 0,
            "estimated": True,
        })
    return lines, issues


def fetch_insufficient_count(conn, target: date_type) -> int | None:
    try:
        row = conn.execute(text(SQL_INSUFFICIENT), {"d": target}).fetchone()
        return int(row[0] or 0)
    except Exception:  # noqa: BLE001 - 참고용 경고라 실패해도 집계는 계속
        return None


def build_day(conn, target: date_type, now: datetime | None = None) -> dict:
    now = now or datetime.now(KST)
    cutoff_at, cutoff_source = resolve_cutoff(conn, target)
    delivery_infos = fetch_delivery_stops(conn, target)
    mode = decide_mode(bool(delivery_infos), now, cutoff_at)

    raw = fetch_order_lines(conn, target)
    pending_raw, issues = fetch_app_pending(conn, target)

    warnings: dict = {}
    if mode == MODE_PREVIEW_OPEN:
        raw = raw + pending_raw
        warnings.update({
            "app_unmatched_address_qty": issues["app_unmatched_address_qty"],
            "app_unmapped_product_qty": issues["app_unmapped_product_qty"],
            "app_blocked_qty": issues["app_blocked_qty"],
            "unconverted_app_qty": 0,
        })
    else:
        # A 방식: 마감 후 남은 미전환 선택은 합계 제외 + 경고
        warnings["unconverted_app_qty"] = issues["app_pending_total_qty"]
        warnings["insufficient_records"] = fetch_insufficient_count(conn, target)

    lines = prepare_lines(raw)

    if mode == MODE_DELIVERY:
        stop_infos = delivery_infos
    else:
        ids = sorted({ln["address_id"] for ln in lines if ln["address_id"] is not None})
        stop_infos = fetch_address_stops(conn, ids)

    targets = internal_targets()
    mark_internal(stop_infos, lines, targets)

    agg = assemble(target, mode, cutoff_at, cutoff_source, stop_infos, lines, warnings)
    agg["internal"] = internal_view(agg, enabled=bool(targets["address_ids"] or targets["account_ids"]))

    live = {s["address_id"] for s in agg["stops"] if s["address_id"] is not None}
    agg["warnings"].update(summarize_cancelled(fetch_cancelled(conn, target), live))
    return agg

