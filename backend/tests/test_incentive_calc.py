import pytest

from app.services.incentive_calc import OVER_MAX_MSG, band_pay, check_bands, day_row

P = check_bands("product", [{"start": 0, "end": 300, "amount": 0}, {"start": 300, "end": 370, "amount": 50},
                            {"start": 370, "end": 440, "amount": 70}, {"start": 440, "end": None, "amount": 90}])
A = check_bands("account", [{"start": 0, "end": 40, "amount": 0}, {"start": 40, "end": 45, "amount": 300},
                            {"start": 45, "end": 50, "amount": 400}, {"start": 50, "end": None, "amount": 500}])
RATE = {"product": P, "account": A}


@pytest.mark.parametrize("q,amt", [(300, 0), (370, 3_500), (400, 7_000), (441, 12_690), (2_000, 153_000)])
def test_product_pay(q, amt):
    assert band_pay(q, P)["amount"] == amt
    assert band_pay(q, P)["over_max"] is False      # 끝값 비움 → 경고 없음


@pytest.mark.parametrize("c,amt", [(40, 0), (43, 900), (47, 2_800), (52, 6_000)])
def test_account_pay(c, amt):
    assert band_pay(c, A)["amount"] == amt


def test_over_max_uses_last_unit():
    b = check_bands("product", [{"start": 0, "end": 300, "amount": 0}, {"start": 300, "end": 1000, "amount": 90}])
    r = band_pay(1_100, b)
    assert r == {"amount": 800 * 90, "excess": 800, "unit": 90, "over_max": True}


@pytest.mark.parametrize("bands,msg", [
    ([{"start": 10, "end": 20, "amount": 1}], "0부터"),
    ([{"start": 0, "end": None, "amount": 0}, {"start": 300, "end": None, "amount": 50}], "마지막 구간에만"),
    ([{"start": 0, "end": 300, "amount": 0}, {"start": 310, "end": None, "amount": 50}], "끊기거나 겹칩니다"),
    ([{"start": 0, "end": None, "amount": 0}], "단가가 있는 구간이 없습니다"),
])
def test_check_bands_errors(bands, msg):
    with pytest.raises(ValueError, match=msg):
        check_bands("product", bands)


STOPS = [{"address_id": 1, "gajung_qty": 200, "mil_qty": 150, "dinner_qty": 30},
         {"address_id": 2, "gajung_qty": 20, "mil_qty": 0, "dinner_qty": 0}]


def test_dinner_reference_only_and_exclusion():
    r = day_row(STOPS, {2: {"id": 9}}, 0, 43, RATE, False, 0)
    assert r["dinner_qty"] == 30 and r["auto_qty"] == 370 and r["product_total"] == 350
    assert r["product_incentive"] == 2_500 and r["account_incentive"] == 900 and r["payable"] == 3_400


def test_need_accounts_holds_payment_but_extras_paid():
    r = day_row(STOPS, {}, 0, None, RATE, False, 20_000)
    assert r["status"] == "need_accounts" and r["payable"] is None and r["total"] == 20_000


def test_held_zeroes_incentive_only():
    r = day_row(STOPS, {}, 0, 43, RATE, True, 20_000)
    assert r["incentive"] == 3_500 + 900 and r["payable"] == 0 and r["total"] == 20_000


def test_delta_and_shared_warning():
    r = day_row(STOPS, {}, -5, 41, RATE, False, 0, {1})
    assert r["product_total"] == 365
    assert any("함께 배정" in w for w in r["warns"])


def test_over_max_warning_text():
    b = {"product": check_bands("product", [{"start": 0, "end": 300, "amount": 0},
                                            {"start": 300, "end": 360, "amount": 50}]), "account": A}
    r = day_row(STOPS, {}, 0, 41, b, False, 0)
    assert any(OVER_MAX_MSG in w for w in r["warns"])


def test_pilot_reference_only():
    st = [{"address_id": 1, "gajung_qty": 310, "mil_qty": 0, "dinner_qty": 5, "pilot_qty": 40}]
    r = day_row(st, {}, 0, 41, RATE, False, 0)
    assert r["pilot_qty"] == 40 and r["dinner_qty"] == 5
    assert r["product_total"] == 310 and r["product_incentive"] == 500