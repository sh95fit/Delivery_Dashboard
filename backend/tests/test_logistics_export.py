from app.services.excel_export import build_xlsx
from app.services.logistics_export import KEYS, view_sheets


def _row(**kw):
    base = {k: 0 for k in KEYS}
    base["cost_ratio"] = None
    base.update(kw)
    return base


VIEW = {
    "from": "2026-10-01", "to": "2026-10-02", "days": 2, "open_days": 2,
    "accounts": [_row(manager_id=12, manager_name="테스트", net_revenue=1000000, labor=200000,
                      fuel_est=5760, cost_total=205760, profit=794240, cost_ratio=20.6)],
    "by_day": [{"date": "2026-10-01", **_row()}, {"date": "2026-10-02", **_row()}],
    "totals": _row(net_revenue=1000000, labor=200000, fuel_est=5760, cost_total=205760,
                   profit=794240, cost_ratio=20.6),
    "issues": [{"level": "warn", "msg": "경고"}, {"level": "info", "msg": "안내"}],
}


def test_sheets():
    name, sheets = view_sheets(VIEW)
    assert name == "물류비_2026-10-01_2026-10-02.xlsx"
    assert [s["title"] for s in sheets] == ["계정별", "일자별", "확인 사항"]
    assert [r["wd"] for r in sheets[1]["rows"]] == ["목", "금"]
    assert [r["level"] for r in sheets[2]["rows"]] == ["안내", "확인", "안내"]
    assert sheets[0]["totals"]["manager_name"] == "합계"


def test_xlsx_bytes():
    _, sheets = view_sheets(VIEW)
    assert build_xlsx(sheets)[:2] == b"PK"
