from datetime import date, datetime

import pytest

from app.services import day_aggregate as da

KST = da.KST
T = date(2026, 10, 1)
CUTOFF = datetime(2026, 9, 30, 14, 30, tzinfo=KST)


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
              "gross_revenue", "refund_amount", "net_revenue")
    for f in fields:
        assert sum(s[f] for s in agg["stops"]) == t[f], f
        assert sum(m[f] for m in agg["managers"]) == t[f], f
    assert sum(m["stops"] for m in agg["managers"]) == t["stops"] == len(agg["stops"])
    assert t["meals"] == t["lunch_meals"] + t["dinner_meals"]
    assert t["meals"] == t["web_qty"] + t["admin_qty"] + t["app_qty"]
    assert sum(v["qty"] for v in agg["by_lineup"].values()) == t["meals"]
    assert sum(v["net_revenue"] for v in agg["by_lineup"].values()) == t["net_revenue"]


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

UUID = "01336133-90d0-4a02-899b-dbe15a06afd7"


def test_delivery_row_uuid_id():
    r = {"delivery_id": UUID, "address_id": 1, "address_name": "A", "detail_address": None,
         "latitude": 37.5, "longitude": 127.0, "delivery_hour": "11:30", "manager_id": 1,
         "manager_name": "M1", "manager_color": "#111", "delivered_at": None}
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

def test_internal_split_excluded_from_customer():
    stops = [_dlv(1, 1, 1, delivered=datetime(2026, 10, 1, 11, 0)), _dlv(2, 102, 1)]
    stops[0]["account_id"] = 10
    stops[1]["account_id"] = 1
    lines = da.prepare_lines([
        _line("web", 1, 10, 4, 3, 26400),
        _line("web", 102, 1, 4, 5, 0),
        _line("web", 102, 1, 23, 2, 4000),
    ])
    ci, cl, ii, il = da.split_internal(stops, lines, {1, 2484})
    agg = da.assemble(T, da.MODE_DELIVERY, CUTOFF, "schedule", ci, cl)
    iagg = da.assemble(T, da.MODE_DELIVERY, CUTOFF, "schedule", ii, il)
    assert agg["totals"]["stops"] == 1 and agg["totals"]["meals"] == 3
    assert agg["totals"]["completed_stops"] == 1
    iv = da.internal_view(iagg)
    assert iv["stops"] == 1 and iv["meals"] == 7 and iv["net_revenue"] == 3636
    pv = da.production_view(agg, iagg)
    assert pv["meals"] == 10 and pv["by_lineup"]["4"]["qty"] == 8
    sv = da.status_view(agg, datetime(2026, 10, 2, 9, 0, tzinfo=KST))
    assert sv["state"] == "RESULT" and sv["incomplete"] == 0


def test_internal_env_parse(monkeypatch):
    monkeypatch.setenv("INTERNAL_ACCOUNT_IDS", "1, 2484,abc")
    assert da.internal_account_ids() == {1, 2484}
    monkeypatch.delenv("INTERNAL_ACCOUNT_IDS")
    assert da.internal_account_ids() == {1, 2484}


def test_route_keeps_delivered_internal_stops():
    cust = [{"address_id": 1}]
    internal = [{"address_id": 380}, {"address_id": 2733}, {"address_id": 102}, {"address_id": 2}]
    out = da.route_stops_of(cust, internal, {2, 102, 2595})
    assert [s["address_id"] for s in out] == [1, 380, 2733]


def test_no_route_env_parse(monkeypatch):
    monkeypatch.delenv("INTERNAL_NO_ROUTE_ADDRESS_IDS", raising=False)
    assert da.internal_no_route_address_ids() == {2, 102, 2595}
    monkeypatch.setenv("INTERNAL_NO_ROUTE_ADDRESS_IDS", "2, 102")
    assert da.internal_no_route_address_ids() == {2, 102}

def test_workload_includes_delivered_internal():
    stops = [_dlv(1, 1, 7), _dlv(2, 380, 9, delivered=datetime(2026, 10, 1, 11, 0)), _dlv(3, 102, 7)]
    stops[0]["account_id"], stops[1]["account_id"], stops[2]["account_id"] = 10, 1, 1
    lines = da.prepare_lines([
        _line("web", 1, 10, 4, 3, 26400),
        _line("web", 380, 1, 4, 11, 0),
        _line("web", 102, 1, 4, 14, 0),
    ])
    ci, cl, ii, il = da.split_internal(stops, lines, {1})
    for s in ii:
        s["is_internal"] = True
    agg = da.assemble(T, da.MODE_DELIVERY, CUTOFF, "schedule", ci, cl)
    ri, rl = da.split_pickup(ii, il, {102})
    wagg = da.assemble(T, da.MODE_DELIVERY, CUTOFF, "schedule", ci + ri, cl + rl)
    ms = {m["manager_id"]: m for m in da.merge_manager_workload(agg["managers"], wagg["managers"])}
    assert ms[9]["stops"] == 0 and ms[9]["net_revenue"] == 0
    assert ms[9]["work_stops"] == 1 and ms[9]["internal_meals"] == 11
    assert ms[7]["work_stops"] == 1 and ms[7]["internal_stops"] == 0
    assert sum(m["stops"] for m in ms.values()) == agg["totals"]["stops"]
    agg["work"] = da.workload_view(wagg)
    sv = da.status_view(agg, datetime(2026, 10, 2, 9, 0, tzinfo=KST))
    assert sv["progress"]["total"] == 2 and sv["incomplete"] == 1
    assert [s["is_internal"] for s in wagg["stops"]].count(True) == 1