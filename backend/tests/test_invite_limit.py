"""P11 Step3-5 초대 재발송 검증 + 발송 제한 (DB 없이 순수 로직)."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.permissions import resolve
from app.services import user_service as svc

NOW = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)


def ago(s):
    return NOW - timedelta(seconds=s)


def _inv(status="pending", hours=24):
    return {"id": 1, "status": status, "expires_at": NOW + timedelta(hours=hours)}


def test_first_send_allowed():
    assert svc.retry_after([], NOW) is None


def test_cooldown_within_minute():
    assert svc.retry_after([ago(20)], NOW) == 40


def test_after_minute_ok():
    assert svc.retry_after([ago(60)], NOW) is None


def test_sixth_in_hour_blocked_until_oldest_leaves():
    assert svc.retry_after([ago(s) for s in (120, 600, 1200, 1800, 3000)], NOW) == 600


def test_window_slides():
    assert svc.retry_after([ago(s) for s in (120, 600, 1200, 1800, 3600)], NOW) is None


def test_both_limits_take_max():
    assert svc.retry_after([ago(s) for s in (10, 600, 1200, 1800, 3500)], NOW) == 100


def test_resend_ok_for_pending_with_rule():
    svc.resend_check(None, _inv(), True, NOW)
    svc.resend_check({"active": True, "activated_at": None}, _inv(), True, NOW)


@pytest.mark.parametrize("acc,inv,rule", [
    ({"active": True, "activated_at": NOW}, _inv(), True),     # 이미 가입
    ({"active": False, "activated_at": None}, _inv(), True),   # 비활성 계정
    (None, None, True),                                         # 초대 없음 / 존재하지 않는 이메일
    (None, _inv("revoked"), True),                              # 취소
    (None, _inv(hours=-1), True),                               # 만료
    (None, _inv("accepted"), True),                             # 수락 완료
    (None, _inv(), False),                                      # 이메일 규칙 없음/비활성
])
def test_resend_rejected(acc, inv, rule):
    with pytest.raises(ValueError):
        svc.resend_check(acc, inv, rule, NOW)


def test_rate_limited_passes_guard_as_429():
    from app.deps import guard

    def boom():
        raise svc.InviteRateLimited(42)

    with pytest.raises(HTTPException) as ei:
        guard(boom)
    assert ei.value.status_code == 429 and ei.value.headers["Retry-After"] == "42"


def test_resend_path_passes_middleware():
    assert resolve("/api/users/kim@lunchlab.me/invitation/resend", "POST") != (None, None)


def test_resend_route_takes_no_client_days():
    from app.main import app
    op = app.openapi()["paths"]["/users/{email}/invitation/resend"]["post"]
    assert "requestBody" not in op
