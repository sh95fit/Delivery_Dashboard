"""S3-P2a 물류비 엑셀 내보내기 — 계정별 · 일자별 · 확인 사항 (화면과 같은 cost_view 결과)."""
from __future__ import annotations

from datetime import date

WD = "월화수목금토일"
MONEY = [
    ("순매출(부가세 제외)", "net_revenue"),
    ("인건비", "labor"),
    ("인건비 예상(기록 없음)", "labor_est"),
    ("연장 예상", "ot_expected"),
    ("데일리 인센티브", "incentive"),
    ("특수 수당", "extras"),
    ("차량비", "vehicle"),
    ("유류비(마감)", "fuel"),
    ("유류비 예상(미마감)", "fuel_est"),
    ("물류비 합계", "cost_total"),
    ("이익", "profit"),
]
KEYS = [k for _, k in MONEY]


def _cols() -> list[tuple[str, str, str]]:
    return [(label, key, "won") for label, key in MONEY] + [("비용률(%)", "cost_ratio", "num")]


def view_sheets(view: dict) -> tuple[str, list[dict]]:
    """cost_view 결과 → (파일명, 시트 목록). DB 없음 → 단위 테스트 대상."""
    cols = _cols()
    tot = view["totals"]
    days = [{**r, "wd": WD[date.fromisoformat(r["date"]).weekday()]} for r in view["by_day"]]
    notes = [{"level": "안내", "msg": f"기간 {view['from']} ~ {view['to']} ({view['days']}일, 영업일 {view['open_days']}일)"}]
    notes += [{"level": "확인" if i["level"] == "warn" else "안내", "msg": i["msg"]} for i in view["issues"]]
    sheets = [
        {"title": "계정별", "columns": [("계정", "manager_name", "text"), *cols],
         "rows": view["accounts"], "totals": {**tot, "manager_name": "합계"}},
        {"title": "일자별", "columns": [("일자", "date", "date"), ("요일", "wd", "text"), *cols],
         "rows": days, "totals": {**tot, "date": "합계"}},
        {"title": "확인 사항", "columns": [("구분", "level", "text"), ("내용", "msg", "text")],
         "rows": notes, "totals": None},
    ]
    return f"물류비_{view['from']}_{view['to']}.xlsx", sheets


def cost_sheets(frm: date, to: date) -> tuple[str, list[dict]]:
    from app.services.logistics_service import cost_view   # 함수 안 import = 테스트에서 DB 없이 view_sheets 사용
    return view_sheets(cost_view(frm, to))
