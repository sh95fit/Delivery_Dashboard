from app.services.revenue_service import combine_days


def _view(date, net, gross, refund, meals, mgr_id=1, estimated=False):
    return {
        "date": date, "estimated": estimated,
        "summary": {"stops": 2, "accounts": 2, "meals": meals, "lunch_meals": meals,
                    "gross_revenue": gross, "refund_amount": refund, "net_revenue": net},
        "managers": [{"manager_id": mgr_id, "manager_name": "A", "stops": 2, "meals": meals,
                      "accounts": 2, "gross_revenue": gross, "refund_amount": refund,
                      "net_revenue": net, "lineups": {"4": {"name": "가정식", "qty": meals, "amount": net}}}],
        "by_lineup": {"4": {"name": "가정식", "meal": "lunch", "qty": meals, "gross_revenue": gross,
                            "refund_amount": refund, "net_revenue": net}},
    }


def test_period_equals_sum_of_days():
    out = combine_days([
        _view("2026-09-29", 31_457_729, 31_521_729, 64_000, 4056),
        _view("2026-09-30", 28_628_816, 28_628_816, 0, 3705),
    ])
    t = out["total"]
    assert t["meals"] == 7761
    assert t["gross_revenue"] == 60_150_545
    assert t["refund_amount"] == 64_000
    assert t["net_revenue"] == 60_086_545 == t["gross_revenue"] - t["refund_amount"]
    assert sum(m["net_revenue"] for m in out["by_manager"]) == t["net_revenue"]
    assert out["by_lineup"]["4"]["amount"] == t["net_revenue"]
    assert out["days"] == 2 and out["estimated_days"] == 0


def test_unassigned_last_and_estimated_days():
    out = combine_days([
        _view("2026-10-01", 100, 100, 0, 1, mgr_id=None, estimated=True),
        _view("2026-10-01", 50, 50, 0, 1, mgr_id=7),
    ])
    assert out["by_manager"][-1]["manager_id"] is None
    assert out["estimated_days"] == 1
