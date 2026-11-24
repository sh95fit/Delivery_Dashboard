"""P11 Step3-3 초대(이메일 사전 등록) + 첫 구글 로그인 시 활성화 — 순수 로직 + 마스터 전용 검증."""
from datetime import datetime, timedelta, timezone

import pytest

from app.permissions import resolve
from app.services import account_service as svc

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def _inv(status="pending", days=1, accepted=False):
    return {"id": 7, "status": status, "expires_at": NOW + timedelta(days=days),
            "accepted_at": NOW if accepted else None}


# ── 이메일·유효기간 정규화 ──
def test_email_lowercased_and_trimmed():
    assert svc.normalize_email("  Kim@LunchLab.me ") == "kim@lunchlab.me"


@pytest.mark.parametrize("bad", ["", "   ", "no-at", "a@b", "a b@c.com"])
def test_email_invalid(bad):
    with pytest.raises(ValueError):
        svc.normalize_email(bad)


def test_days_default_and_range():
    assert svc.normalize_days(None) == 7
    assert svc.normalize_days(3) == 3
    for bad in (0, -1, 31, "x"):
        with pytest.raises(ValueError):
            svc.normalize_days(bad)


# ── 초대 상태 (만료는 저장하지 않고 계산) ──
def test_state_pending():
    assert svc.invitation_state(_inv(), NOW) == "pending"


def test_state_expired():
    assert svc.invitation_state(_inv(days=-1), NOW) == "expired"


def test_state_accepted_and_revoked_win_over_expiry():
    assert svc.invitation_state(_inv("accepted", days=-1), NOW) == "accepted"
    assert svc.invitation_state(_inv("revoked", days=-1), NOW) == "revoked"


# ── 로그인 시 활성화 판단 ──
def test_activate_when_valid_invite_and_rule():
    assert svc.decide_activation(None, _inv(), True, NOW) == "activate"


def test_existing_unactivated_account_also_activates():
    acc = {"id": 1, "activated_at": None, "active": True}
    assert svc.decide_activation(acc, _inv(), True, NOW) == "activate"


def test_no_rule_no_activation():
    assert svc.decide_activation(None, _inv(), False, NOW) == "skip"


def test_expired_invite_no_activation():
    assert svc.decide_activation(None, _inv(days=-1), True, NOW) == "skip"


def test_no_invite_no_activation():
    assert svc.decide_activation(None, None, True, NOW) == "skip"


def test_already_activated_is_skip():
    acc = {"id": 1, "activated_at": NOW, "active": True}
    assert svc.decide_activation(acc, _inv(), True, NOW) == "skip"


def test_deactivated_account_not_revived_by_invite():
    acc = {"id": 1, "activated_at": None, "active": False}
    assert svc.decide_activation(acc, _inv(), True, NOW) == "skip"


# ── 마스터 전용 ──
def test_router_is_super_only():
    from app.deps import require_super
    from app.routers import account_routes as r
    assert any(d.dependency is require_super for d in r.router.dependencies)


@pytest.mark.parametrize("path,method", [
    ("/accounts", "GET"), ("/accounts/3/active", "PUT"),
    ("/invitations", "GET"), ("/invitations", "POST"), ("/invitations/5", "DELETE"),
])
def test_account_paths_pass_middleware(path, method):
    assert resolve(path, method) != (None, None)
