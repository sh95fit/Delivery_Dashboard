from datetime import date, datetime

import pytest

from app.services import day_aggregate as da

KST = da.KST
T = date(2026, 10, 1)
CUTOFF = datetime(2026, 9, 30, 14, 30, tzinfo=KST)
UUID = "01336133-90d0-4a02-899b-dbe15a06afd7"


def _addr(aid, mgr=1, lat=37.5, lng=127.0):
    return {"key": f"a{aid}", "delivery_id": f"preview-{aid}", "route_item_id": aid,
            "address_id": aid, "address_name": f"주소{aid}", "detail_address": None,
            "latitude": lat, "longitude": lng, "delivery_hour": "11:30",
            "manager_id": mgr, "manager_name": f"M{mgr}" if mgr else None,
            "manager_color": "#111" if mgr else None, "delivered_at": None}


def _dlv(did, aid, mgr, delivered=None):
    d = _addr(aid, mgr)
    d.update({"key": f"d{did}", "delivery_id": str(did), "route_item_id": did, "delivered_at": delivered})
    return d


def _line(src, aid, acc, pid, qty, gross=0, refund_qty=0, refund=0, est=False):
    return {"src": src, "address_id": aid, "account_key": acc, "product_id": pid,
            "product_name": str(pid), "qty": qty, "gross": gross,
            "refund_qty": refund_qty, "refund": refund, "estimated": est}


def _agg(stops, lines, mode=da.MODE_PREVIEW_OPEN):
    return da.assemble(T, mode, CUTOFF, "schedule", stops, da.prepare_lines(lines))


def _mixed():
    return _agg(
        [_addr(1), _addr(2), _addr(3, mgr=2), _addr(4, mgr=None, lat=None)],
        [
            _line("web", 1, 10, 4, 3, 26400),
            _line("app_pending", 1, 10, 23, 2, 17600, est=True),
            _line("app_pending", 2, 20, 29, 1, 8800, est=True),
            _line("admin", 3, 30, 2, 5, 40000),
            _line("web", 3, 31, 4, 6, 52800, refund_qty=1, refund=8800),
            _line("app", 4, 40, 4, 2, 17600),
        ],
    )


def _check_invariants(agg):
    t = agg["totals"]
    fields = ("meals", "lunch_meals", "dinner_meals", "web_qty", "admin_qty", "app_qty",
              "gross_revenue", "refund_amount", "net_revenue", "internal_meals", "internal_net")
    for f in fields:
        assert sum(s[f] for s in agg["stops"]) == t[f], f
        assert sum(m[f] for m in agg["managers"]) == t[f], f
    assert sum(m["stops"] for m in agg["managers"]) == t["stops"] == len(agg["stops"])
    assert t["meals"] == t["lunch_meals"] + t["dinner_meals"]
    assert t["meals"] == t["web_qty"] + t["admin_qty"] + t["app_qty"]
    assert sum(v["qty"] for v in agg["by_lineup"].values()) == t["meals"]
    assert sum(v["net_revenue"] for v in agg["by_lineup"].values()) == t["net_revenue"]
    assert sum(v["internal_net"] for v in agg["by_lineup"].values()) == t["internal_net"]


def test_ex_vat():
    assert da.ex_vat(8800) == 8000
    assert da.ex_vat(52800) == 48000
    assert da.ex_vat(0) == 0
    assert da.ex_vat(1) == 1
    assert da.ex_vat(5) == 5
    assert da.ex_vat(6) == 5


def test_cutoff_schedule_utc_to_kst():
    at, src = da.cutoff_from_schedule(datetime(2026, 9, 30, 5, 30), T)
    assert src == "schedule"
    assert at == datetime(2026, 9, 30, 14, 30, tzinfo=KST)
    at2, src2 = da.cutoff_from_schedule(None, T)
    assert src2 == "default" and at2 == datetime(2026, 9, 30, 14, 30, tzinfo=KST)


def test_decide_mode():
    before = datetime(2026, 9, 30, 12, 0, tzinfo=KST)
    after = datetime(2026, 9, 30, 15, 0, tzinfo=KST)
    assert da.decide_mode(True, before, CUTOFF) == da.MODE_DELIVERY
    assert da.decide_mode(False, before, CUTOFF) == da.MODE_PREVIEW_OPEN
    assert da.decide_mode(False, after, CUTOFF) == da.MODE_PREVIEW_CLOSED


def test_web_app_same_address_merged():
    agg = _agg([_addr(1), _addr(2)], [
        _line("web", 1, 10, 4, 3, 26400),
        _line("app_pending", 1, 10, 23, 2, 17600, est=True),
        _line("app_pending", 2, 20, 29, 1, 8800, est=True),
    ])
    t = agg["totals"]
    assert t["stops"] == 2 and t["accounts"] == 2
    assert t["meals"] == 6 and t["web_qty"] == 3 and t["app_qty"] == 3
    assert t["gross_revenue"] == 48000 and t["estimated_revenue"] == 24000
    s1 = next(s for s in agg["stops"] if s["address_id"] == 1)
    assert s1["meals"] == 5 and s1["accounts"] == 1
    _check_invariants(agg)


def test_refund_subtracted():
    agg = _agg([_addr(1)], [_line("web", 1, 10, 4, 6, 52800, refund_qty=1, refund=8800)])
    t = agg["totals"]
    assert (t["gross_revenue"], t["refund_amount"], t["net_revenue"]) == (48000, 8000, 40000)
    assert t["meals"] == 6 and t["refund_qty"] == 1


def test_lunch_dinner_split():
    agg = _agg([_addr(1)], [
        _line("web", 1, 10, 4, 3, 26400),
        _line("admin", 1, 11, 2, 5, 40000),
    ])
    t = agg["totals"]
    assert t["lunch_meals"] == 3 and t["dinner_meals"] == 5 and t["admin_qty"] == 5
    assert agg["by_lineup"]["2"]["meal"] == "dinner"
    assert t["gross_revenue"] == 24000 + 36364


def test_delivery_mode_duplicate_and_unplaced():
    agg = _agg(
        [_dlv(1, 1, 1, delivered=datetime(2026, 10, 1, 11, 0)), _dlv(2, 1, 2), _dlv(3, 3, None)],
        [_line("web", 1, 10, 4, 4, 35200), _line("web", 9, 90, 4, 2, 17600)],
        mode=da.MODE_DELIVERY,
    )
    t = agg["totals"]
    assert t["stops"] == 3 and t["meals"] == 4
    assert t["completed_stops"] == 1 and t["unassigned_stops"] == 1
    assert agg["warnings"]["unplaced_qty"] == 2 and agg["warnings"]["unplaced_lines"] == 1
    assert next(s for s in agg["stops"] if s["delivery_id"] == "2")["meals"] == 0
    _check_invariants(agg)


def test_no_coord_stop_counted_and_flagged():
    agg = _agg([_addr(1, lat=None)], [_line("web", 1, 10, 4, 3, 26400)])
    assert agg["totals"]["stops"] == 1 and agg["totals"]["no_coord_stops"] == 1
    s = agg["stops"][0]
    assert s["has_coord"] is False and s["latitude"] is None


def test_mixed_invariants():
    _check_invariants(_mixed())


def test_card_equals_table():
    agg = _mixed()
    now = datetime(2026, 9, 30, 12, 0, tzinfo=KST)
    sv, dv = da.status_view(agg, now), da.delivery_view(agg)
    assert sv["state"] == "PREVIEW"
    assert sv["progress"]["total"] == dv["summary"]["stops"] == len(dv["stops"])
    assert sv["estimate"]["estimated_meals"] == dv["summary"]["meals"]
    assert sv["estimate"]["estimated_accounts"] == dv["summary"]["accounts"]
    assert sv["estimate"]["estimated_net_revenue"] == dv["summary"]["net_revenue"]


@pytest.mark.parametrize("hour", [15, 23])
def test_closed_future_preview_not_zero(hour):
    agg = _agg([_addr(1)], [_line("web", 1, 10, 4, 3, 26400)], mode=da.MODE_PREVIEW_CLOSED)
    sv = da.status_view(agg, datetime(2026, 9, 30, hour, 0, tzinfo=KST))
    assert sv["state"] == "PREVIEW"
    assert sv["progress"]["total"] == 1 and sv["estimate"]["estimated_meals"] == 3


def test_delivery_row_uuid_id():
    r = {"delivery_id": UUID, "address_id": 1, "account_id": 10, "address_name": "A",
         "detail_address": None, "latitude": 37.5, "longitude": 127.0, "delivery_hour": "11:30",
         "manager_id": 1, "manager_name": "M1", "manager_color": "#111", "delivered_at": None}
    info = da.delivery_row_to_info(r)
    assert info["delivery_id"] == UUID and info["route_item_id"] == UUID
    agg = da.assemble(T, da.MODE_DELIVERY, CUTOFF, "schedule", [info],
                      da.prepare_lines([_line("web", 1, 10, 4, 2, 17600)]))
    assert agg["stops"][0]["delivery_id"] == UUID and agg["totals"]["meals"] == 2


def test_cancelled_summary():
    rows = [
        {"order_id": 1, "source": "app", "address_id": 5, "qty": 3},
        {"order_id": 2, "source": "web", "address_id": 1, "qty": 2},
        {"order_id": 3, "source": "web", "address_id": 9, "qty": 0},
    ]
    s = da.summarize_cancelled(rows, {1})
    assert s["cancelled_orders"] == 2 and s["cancelled_qty"] == 5
    assert s["cancelled_stops"] == 1
    assert s["cancelled_by_source"]["app"] == {"orders": 1, "qty": 3}


def test_past_date_incomplete_is_result():
    agg = _agg([_dlv(1, 1, 1, delivered=datetime(2026, 10, 1, 11, 0)), _dlv(2, 2, 1)],
               [_line("web", 1, 10, 4, 1, 8800), _line("web", 2, 20, 4, 1, 8800)],
               mode=da.MODE_DELIVERY)
    sv = da.status_view(agg, datetime(2026, 10, 2, 9, 0, tzinfo=KST))
    assert sv["state"] == "RESULT" and sv["incomplete"] == 1


def test_future_delivery_preview_has_estimate():
    agg = _agg([_dlv(1, 1, 1)], [_line("web", 1, 10, 4, 3, 26400)], mode=da.MODE_DELIVERY)
    sv = da.status_view(agg, datetime(2026, 9, 30, 20, 0, tzinfo=KST))
    assert sv["state"] == "PREVIEW"
    assert sv["estimate"] is not None and sv["estimate"]["estimated_meals"] == 3


# ---- 직원식: 일감·실적 수량은 포함, 매출에서만 제외 ----
def _internal_case(targets):
    done = datetime(2026, 10, 1, 11, 0)
    stops = [_dlv(1, 1, 1, delivered=done), _dlv(2, 102, 1), _dlv(3, 380, 9, delivered=done)]
    stops[0]["account_id"], stops[1]["account_id"], stops[2]["account_id"] = 10, 1, 1
    lines = da.prepare_lines([
        _line("web", 1, 10, 4, 3, 26400),
        _line("web", 102, 1, 4, 5, 0),
        _line("web", 102, 1, 23, 2, 4000),
        _line("web", 380, 1, 4, 11, 0),
    ])
    da.mark_internal(stops, lines, targets)
    return da.assemble(T, da.MODE_DELIVERY, CUTOFF, "schedule", stops, lines)


def test_no_targets_everything_is_revenue():
    agg = _internal_case({"address_ids": set(), "account_ids": set()})
    t = agg["totals"]
    assert t["stops"] == 3 and t["meals"] == 21
    assert t["net_revenue"] == 24000 + 3636 and t["internal_meals"] == 0
    assert da.internal_view(agg, enabled=False)["places"] == []
    _check_invariants(agg)


def test_internal_address_excluded_from_revenue_only():
    agg = _internal_case({"address_ids": {102}, "account_ids": set()})
    t = agg["totals"]
    assert t["stops"] == 3 and t["meals"] == 21 and t["completed_stops"] == 2
    assert t["net_revenue"] == 24000
    assert t["internal_stops"] == 1 and t["internal_meals"] == 7 and t["internal_net"] == 3636
    ms = {m["manager_id"]: m for m in agg["managers"]}
    assert ms[1]["stops"] == 2 and ms[1]["meals"] == 10 and ms[1]["internal_meals"] == 7
    assert ms[9]["stops"] == 1 and ms[9]["meals"] == 11 and ms[9]["internal_meals"] == 0
    iv = da.internal_view(agg)
    assert iv["stops"] == 1 and iv["meals"] == 7 and iv["net_revenue"] == 3636
    assert iv["by_lineup"]["23"] == {"name": "23", "meal": "lunch", "qty": 2, "net_revenue": 3636}
    assert agg["by_lineup"]["23"]["qty"] == 2 and agg["by_lineup"]["23"]["net_revenue"] == 0
    sv = da.status_view(agg, datetime(2026, 10, 2, 9, 0, tzinfo=KST))
    assert sv["progress"]["total"] == 3 and sv["incomplete"] == 1
    _check_invariants(agg)


def test_internal_by_account():
    agg = _internal_case({"address_ids": set(), "account_ids": {1}})
    t = agg["totals"]
    assert t["internal_stops"] == 2 and t["internal_meals"] == 18 and t["net_revenue"] == 24000
    _check_invariants(agg)


def test_internal_targets_env_and_db(monkeypatch):
    from app.services import internal_target_service as its
    monkeypatch.setattr(its, "active_targets", lambda: {"address_ids": set(), "account_ids": set()})
    monkeypatch.delenv("INTERNAL_ADDRESS_IDS", raising=False)
    monkeypatch.delenv("INTERNAL_ACCOUNT_IDS", raising=False)
    assert da.internal_targets() == {"address_ids": set(), "account_ids": set()}

    monkeypatch.setenv("INTERNAL_ADDRESS_IDS", "2, 102,abc")
    monkeypatch.setenv("INTERNAL_ACCOUNT_IDS", "2484")
    assert da.internal_targets() == {"address_ids": {2, 102}, "account_ids": {2484}}

    monkeypatch.setattr(its, "active_targets", lambda: {"address_ids": {2595}, "account_ids": {1}})
    assert da.internal_targets() == {"address_ids": {2, 102, 2595}, "account_ids": {1, 2484}}


def test_internal_targets_db_failure_falls_back_to_env(monkeypatch):
    from app.services import internal_target_service as its

    def boom():
        raise RuntimeError("dash db down")

    monkeypatch.setattr(its, "active_targets", boom)
    monkeypatch.setenv("INTERNAL_ADDRESS_IDS", "2")
    monkeypatch.delenv("INTERNAL_ACCOUNT_IDS", raising=False)
    assert da.internal_targets() == {"address_ids": {2}, "account_ids": set()}
