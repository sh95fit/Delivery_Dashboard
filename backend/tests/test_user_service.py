"""P11 Step3-4 사용자 탭 = 이메일 규칙 + 계정 + 초대 통합. 도메인 규칙 없음."""
from datetime import datetime, timedelta, timezone

import pytest

from app.permissions import resolve
from app.services import user_service as svc

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def _inv(status="pending", hours=24, email="kim@lunchlab.me"):
    return {"email": email, "status": status, "expires_at": NOW + timedelta(hours=hours),
            "memo": None, "created_at": NOW}


def _acc(email="kim@lunchlab.me", active=True, activated=True, is_super=False):
    return {"email": email, "active": active, "is_super": is_super,
            "activated_at": NOW if activated else None, "last_login_at": None}


# ── 상태 계산 ──
def test_active():
    assert svc.user_status(_acc(), None, NOW) == ("active", None)


def test_inactive_wins_over_everything():
    assert svc.user_status(_acc(active=False), _inv(), NOW) == ("inactive", None)


def test_invited_with_days_left():
    assert svc.user_status(None, _inv(hours=24 * 7), NOW) == ("invited", 7)


def test_invited_partial_day_rounds_up():
    assert svc.user_status(None, _inv(hours=5), NOW) == ("invited", 1)


def test_expired():
    assert svc.user_status(None, _inv(hours=-1), NOW) == ("expired", None)


def test_revoked():
    assert svc.user_status(None, _inv("revoked"), NOW) == ("revoked", None)


def test_unactivated_account_follows_invite():
    assert svc.user_status(_acc(activated=False), _inv(hours=48), NOW) == ("invited", 2)


def test_rule_only_is_none():
    assert svc.user_status(None, None, NOW) == ("none", None)


# ── 비활성화 가능 여부 ──
def test_cannot_deactivate_super_or_self():
    assert svc.can_deactivate("a@x.com", True, "me@x.com") is False
    assert svc.can_deactivate("me@x.com", False, " ME@x.com ") is False
    assert svc.can_deactivate("a@x.com", False, "me@x.com") is True


# ── 목록 병합: 이메일당 1줄, 최신 초대 기준, 마스터 먼저 ──
def test_build_rows_one_per_email():
    rules = [{"value": "Kim@lunchlab.me", "permission_set_id": 3, "permission_set_name": "현장"}]
    accounts = [_acc("boss@lunchlab.me", is_super=True)]
    invites = [_inv("pending", 48), _inv("revoked", -100)]  # created_at DESC 순서
    rows = svc.build_rows(rules, accounts, invites, NOW, "boss@lunchlab.me")
    assert [r["email"] for r in rows] == ["boss@lunchlab.me", "kim@lunchlab.me"]
    boss, kim = rows
    assert boss["is_me"] and not boss["can_deactivate"]
    assert kim["status"] == "invited" and kim["days_left"] == 2
    assert kim["permission_set_id"] == 3


# ── 도메인 규칙 제거 확인 ──
def test_no_domain_in_permission_sql():
    from app.services import account_service, permission_service
    assert "domain" not in permission_service._SQL_PERM.text
    assert "domain" not in account_service._SQL_HAS_RULE


# ── 마스터 전용 + 미들웨어 통과 ──
def test_router_is_super_only():
    from app.deps import require_super
    from app.routers import user_routes as r
    assert any(d.dependency is require_super for d in r.router.dependencies)


@pytest.mark.parametrize("path,method", [
    ("/users", "GET"), ("/users", "POST"),
    ("/users/kim@lunchlab.me/permission-set", "PUT"),
    ("/users/kim@lunchlab.me/active", "PUT"),
    ("/users/kim@lunchlab.me/invitation", "DELETE"),
])
def test_user_paths_pass_middleware(path, method):
    assert resolve(path, method) != (None, None)

def test_can_delete_only_inactive_normal_user():
    from app.services.user_service import can_delete
    assert can_delete("a@x.com", False, False, "me@x.com") is True
    assert can_delete("a@x.com", False, True, "me@x.com") is False   # 활성 계정
    assert can_delete("a@x.com", True, False, "me@x.com") is False   # 마스터
    assert can_delete("me@x.com", False, False, "me@x.com") is False # 본인
    
def test_can_clear_invite_only_closed():
    from app.services.user_service import can_clear_invite
    assert can_clear_invite("expired") and can_clear_invite("revoked") and can_clear_invite("none")
    assert not can_clear_invite("invited") and not can_clear_invite("active") and not can_clear_invite("inactive")