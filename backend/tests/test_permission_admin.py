"""P11 Step3-2 권한셋 관리 — 순수 로직 + 마스터 전용 검증. (접근 규칙은 이메일 전용, user_service에서 관리)"""
import pytest
from fastapi import HTTPException

from app.permissions import PAGE_KEYS, resolve
from app.services import permission_admin_service as svc


# ── 권한셋 grants 정규화 ──
def test_grants_fill_all_page_keys():
    g = svc.normalize_grants({"dashboard": {"R": True}})
    assert set(g) == set(PAGE_KEYS)
    assert g["dashboard"] == {"R": True, "C": False, "U": False, "D": False}
    assert g["worklogs"] == {"R": False, "C": False, "U": False, "D": False}


def test_grants_without_R_drop_CUD():
    g = svc.normalize_grants({"vehicles": {"R": False, "C": True, "U": True, "D": True}})
    assert g["vehicles"] == {"R": False, "C": False, "U": False, "D": False}


def test_grants_unknown_key_rejected():
    with pytest.raises(ValueError):
        svc.normalize_grants({"routes": {"R": True}})      # 041에서 제거된 옛 키


def test_grants_unknown_op_ignored():
    g = svc.normalize_grants({"sales": {"R": True, "X": True}})
    assert g["sales"] == {"R": True, "C": False, "U": False, "D": False}


def test_set_name_required():
    with pytest.raises(ValueError):
        svc.normalize_name("   ")


# ── 규칙 CRUD·도메인 지원 제거 확인 ──
def test_rule_crud_removed():
    for name in ("normalize_rule", "pick_rule", "list_rules", "create_rule",
                 "update_rule", "delete_rule", "_DOMAIN"):
        assert not hasattr(svc, name)


# ── 마스터 전용 ──
def test_require_super_blocks_non_master(monkeypatch):
    from app import deps
    from app.services import permission_service
    monkeypatch.setattr(permission_service, "is_super", lambda e: False)
    with pytest.raises(HTTPException) as ei:
        deps.require_super("user@lunchlab.me")
    assert ei.value.status_code == 403


def test_router_is_super_only():
    from app.deps import require_super
    from app.routers import permission_admin_routes as r
    assert any(d.dependency is require_super for d in r.router.dependencies)


@pytest.mark.parametrize("path,method", [
    ("/permission-sets", "POST"), ("/api/permission-sets/3", "PUT"),
    ("/users", "GET"), ("/api/users", "POST"),
    ("/api/users/kim@lunchlab.me/permission-set", "PUT"),
    ("/api/users/kim@lunchlab.me/active", "PUT"),
    ("/api/users/kim@lunchlab.me/invitation", "DELETE"),
])
def test_admin_paths_pass_middleware(path, method):
    # 매칭 없음 = (None, None) = 기본 차단 → 마스터도 막힘. 규칙이 있어야 함
    assert resolve(path, method) != (None, None)


@pytest.mark.parametrize("path,method", [
    ("/access-rules", "GET"), ("/api/access-rules/3", "DELETE"),
    ("/accounts", "GET"),
])
def test_removed_admin_paths_blocked(path, method):
    # 3-4c/3-4d에서 제거한 주소는 규칙이 없어 기본 차단되어야 함
    assert resolve(path, method) == (None, None)
