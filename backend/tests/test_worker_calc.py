from datetime import time

from app.services.worker_calc import (
    minutes_between, month_base_pay, overtime_minutes, overtime_pay,
    resolve_accounts, vat_of, worked_paid_minutes,
)


def test_month_pay_matches_september_sheet():
    assert month_base_pay([(126 * 60 + 34, 16000)]) == 2_025_067   # 김도연
    assert month_base_pay([(139 * 60 + 5, 27500)]) == 3_824_792    # 이재일
    assert month_base_pay([(153 * 60 + 24, 27500)]) == 4_218_500   # 조영진


def test_month_pay_rate_change_mid_month():
    assert month_base_pay([(600, 15000), (600, 16000)]) == 310_000


def test_vat():
    assert 4_218_500 + vat_of(4_218_500, True) == 4_640_350        # 조영진 시트 값
    assert vat_of(3_824_792, True) == 382_479
    assert vat_of(1_000_000, False) == 0


def test_worked_minutes():
    assert worked_paid_minutes(time(7), time(13, 13), 0, True) == 373
    assert worked_paid_minutes(time(7), time(13, 13), 30, False) == 343
    assert minutes_between(time(14), time(13)) == 0
    assert minutes_between(None, time(13)) == 0


def test_overtime():
    base = 390                                    # 7:00~13:30 유급
    assert overtime_minutes(422, base) == 32      # 14:02 퇴근
    assert overtime_minutes(380, base) == 0
    assert overtime_pay(32, 30, 8000) == 8000
    assert overtime_pay(29, 30, 8000) == 0
    assert overtime_pay(65, 30, 8000) == 16000
    assert overtime_pay(32, 0, 8000) == 0


def test_resolve_accounts():
    fixed = {101: 1, 102: 2, 103: 3}
    assert resolve_accounts(fixed, {}) == {1: 101, 2: 102, 3: 103}
    assert resolve_accounts(fixed, {2: 101}) == {2: 101, 3: 103}          # 101이 그날 2번 계정
    assert resolve_accounts(fixed, {3: None}) == {1: 101, 2: 102}         # 3번 계정 그날 미사용
    assert resolve_accounts(fixed, {2: 104}) == {1: 101, 2: 104, 3: 103}  # 대타
