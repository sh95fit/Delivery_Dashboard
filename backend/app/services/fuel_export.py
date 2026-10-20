"""S3-P1b-2b-3 유류비 엑셀 내보내기 — 주유 기록(주유일·차량번호 전체·사용자·금액) · 차량별 · 매니저별."""
from __future__ import annotations

import logging

from app.services import dash_db
from app.services.fuel_log_calc import log_cost, month_bounds
from app.services.fuel_log_service import FUEL_LABEL, SQL_ASSIGNS, SQL_LOGS, log_ref, month_summary, price_rows, users_on
from app.services.fuel_price_service import daily_prices
from app.services.manager_service import _rds_managers

logger = logging.getLogger("api")


def manager_names() -> dict[int, str]:
    """운영 DB 매니저 이름. 터널 장애 시 빈 dict → '#번호'로 표시하고 내보내기는 계속."""
    try:
        return {m["manager_id"]: (m["name"] or f"#{m['manager_id']}") for m in _rds_managers()}
    except Exception:  # noqa: BLE001
        logger.warning("매니저 이름 조회 실패 — 번호로 내보냄", exc_info=True)
        return {}


def _kind(d: dict) -> str:
    out = []
    for ft in ("gasoline", "diesel", "lpg", "ev"):
        c = d.get(ft)
        if c:
            k = "직접 입력" if c["source"] == "manual" else ("오피넷 확정" if c["confirmed"] else "오피넷 당일 게시")
            if k not in out:
                out.append(k)
    return ", ".join(out) or "없음"


def month_sheets(month: str) -> tuple[str, list[dict]]:
    f, t = month_bounds(month)
    daily = daily_prices(month)          # 빠진 날 오피넷 단가를 먼저 채운 뒤 집계
    s = month_summary(month)
    names = manager_names()
    prices = price_rows(f, t)    

    def who(mid):
        return "계정 미지정" if mid is None else names.get(mid, f"#{mid}")

    assigns = dash_db.rows(SQL_ASSIGNS)
    logs = []
    for r in dash_db.rows(SQL_LOGS + " ORDER BY l.fuel_date, v.plate_no, l.id", {"f": f, "t": t}):
        ded = bool(r["vat_deductible"])
        users = users_on(assigns, r["fuel_date"]).get(r["vehicle_id"], [])
        ref = log_ref(r, prices)        
        logs.append({
            "date": r["fuel_date"], "plate": r["plate_no"],
            "users": ", ".join(who(m) for m in users) or "배정 없음",
            "fuel": FUEL_LABEL.get(r["fuel_type"], r["fuel_type"]),
            "qty": float(r["quantity"]) if r["quantity"] is not None else None,
            "unit": float(r["unit_price"]) if r["unit_price"] is not None else None,
            "ref": ref["ref_price"], "ref_date": ref["ref_date"], "ref_diff": ref["ref_diff"],            
            "supply": int(r["supply_amount"]), "vat": int(r["vat_amount"]), "total": int(r["total_amount"]),
            "ded": "공제" if ded else "불공제", "cost": log_cost(r, ded),
            "src": "엑셀" if r["source"] == "excel" else "직접 입력",
            "memo": r.get("memo"), "by": r.get("created_by"),
        })
    tt = s["totals"]
    plates = {v["vehicle_id"]: v["plate_no"] for v in s["vehicles"]}
    sheets = [
        {"title": "주유 기록", "columns": [
            ("주유일자", "date", "date"), ("차량번호", "plate", "text"), ("사용자", "users", "text"),
            ("연료", "fuel", "text"), ("수량(L·kWh)", "qty", "qty"), ("단가", "unit", "num"),
            ("오피넷 단가", "ref", "num"), ("단가 기준일", "ref_date", "date"), ("단가 차이(%)", "ref_diff", "num"),            
            ("공급가액", "supply", "won"), ("부가세", "vat", "won"), ("합계", "total", "won"),
            ("부가세 공제", "ded", "text"), ("물류비 반영액", "cost", "won"),
            ("입력 방식", "src", "text"), ("메모", "memo", "text"), ("입력자", "by", "text")],
         "rows": logs,
         "totals": {"date": "합계", "qty": tt["quantity"], "supply": tt["supply"], "vat": tt["vat"],
                    "total": tt["total"], "cost": tt["cost"]}},
        {"title": "차량별", "columns": [
            ("차량번호", "plate", "text"), ("연료", "fuel", "text"), ("부가세 공제", "ded", "text"),
            ("주유 횟수", "count", "num"), ("수량(L·kWh)", "qty", "qty"), ("공급가액", "supply", "won"),
            ("부가세", "vat", "won"), ("합계", "total", "won"), ("물류비 반영액", "cost", "won"),
            ("실제 평균 단가", "avg_unit", "num"), ("오피넷 평균 단가", "avg_ref", "num"), ("단가 차이(%)", "ref_diff", "num")],
         "rows": [{"plate": v["plate_no"], "fuel": FUEL_LABEL.get(v["fuel_type"], v["fuel_type"]),
                   "ded": "공제" if v["vat_deductible"] else "불공제", "count": v["count"], "qty": v["quantity"],
                   "supply": v["supply"], "vat": v["vat"], "total": v["total"], "cost": v["cost"],
                   "avg_unit": v["avg_unit"], "avg_ref": v["avg_ref"], "ref_diff": v["ref_diff"]}
                  for v in s["vehicles"]],
         "totals": {"plate": "합계", "count": tt["count"], "qty": tt["quantity"], "supply": tt["supply"],
                    "vat": tt["vat"], "total": tt["total"], "cost": tt["cost"]}},
        {"title": "매니저별", "columns": [
            ("매니저", "name", "text"), ("사용 차량", "plates", "text"),
            (f"유류비 (영업일 {s['open_days']}일 배분)", "cost", "won")],
         "rows": [{"name": who(m["manager_id"]),
                   "plates": ", ".join(plates.get(v) or f"#{v}" for v in m["vehicle_ids"]), "cost": m["cost"]}
                  for m in s["managers"]],
         "totals": {"name": "합계", "cost": sum(m["cost"] for m in s["managers"])}},
        {"title": "일자별 단가", "columns": [
            ("일자", "date", "date"), ("휘발유(원/L)", "gasoline", "num"), ("경유(원/L)", "diesel", "num"),
            ("LPG(원/L)", "lpg", "num"), ("전기(원/kWh)", "ev", "num"), ("구분", "kind", "text")],
         "rows": [{"date": d["date"], **{ft: (d[ft] or {}).get("price") for ft in ("gasoline", "diesel", "lpg", "ev")},
                   "kind": _kind(d)} for d in daily["days"]],
         "totals": None},        
    ]
    status = "마감" if s["closed"] else "예상"
    return f"유류비_{s['month']}_{status}.xlsx", sheets
