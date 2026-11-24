from app import permissions
from app.permissions import resolve
from app.services import permission_service as ps

OLD_KEYS = {"routes", "fuel", "worklog_close", "worklog_export", "incentive_rates"}


def test_write_ops_map_to_page():
    assert resolve("/worklogs/day/2026-10-01", "PUT") == ("worklogs", "U")
    assert resolve("/fuel/logs", "POST") == ("vehicles", "C")          # 유류비 → 차량
    assert resolve("/workers/rates/5", "DELETE") == ("workers", "D")


def test_merged_pages():
    # 근무 마감/재오픈 → 근무 U, 내보내기 → 근무 R
    assert resolve("/worklogs/close", "POST") == ("worklogs", "U")
    assert resolve("/worklogs/reopen", "POST") == ("worklogs", "U")
    assert resolve("/worklogs/export", "GET") == ("worklogs", "R")
    assert resolve("/worklogs/export/plan", "GET") == ("worklogs", "R")
    # 인센티브 단가·품목·특수수당 → 인센티브 R/U
    assert resolve("/incentive/rates", "GET") == ("incentive", "R")
    assert resolve("/incentive/rates", "POST") == ("incentive", "U")
    assert resolve("/incentive/extra-items/3", "DELETE") == ("incentive", "U")
    assert resolve("/incentive/extras", "PUT") == ("incentive", "U")
    # 경로 → 대시보드
    assert resolve("/routes/2026-11-19/refresh", "POST") == ("dashboard", "C")
    assert resolve("/routes/2026-11-19/7/preview", "POST") == ("dashboard", "R")
    assert resolve("/routes/2026-11-19/preview-all", "POST") == ("dashboard", "R")
    assert resolve("/routes/2026-11-19", "GET") == ("dashboard", "R")
    # 유류비 → 차량
    assert resolve("/fuel/export", "GET") == ("vehicles", "R")
    assert resolve("/fuel/logs", "GET") == ("vehicles", "R")


def test_login_only_and_unmapped():
    assert resolve("/me", "GET") == (None, "R")
    assert resolve("/managers", "GET")[0] is None
    assert resolve("/vehicles", "GET")[0] is None
    assert resolve("/admin", "GET") == (None, None)
    assert resolve("/allowlist", "GET") == (None, None)
    assert resolve("/internal-targets", "POST") == ("internal", "C")
    assert resolve("/internal-targets/search", "GET") == ("internal", "C")
    assert resolve("/logistics/export", "GET") == ("logistics", "C")
    assert resolve("/workers/import/accounts", "GET") == ("workers", "C")
    assert resolve("/nonsense", "GET") == (None, None)


def test_api_prefix_and_order():
    assert resolve("/api/fuel/logs", "POST") == ("vehicles", "C")
    assert resolve("/worklogs/close/check", "GET") == ("worklogs", "R")


def test_rules_use_only_official_keys():
    """RULES의 페이지키는 공식 키 목록 안에만 있어야 하고, 옛 키는 없어야 한다."""
    pages = {page for _, _, page, _ in permissions.RULES if page}
    assert pages <= set(permissions.PAGE_KEYS)
    assert not (pages & OLD_KEYS)
    assert not (set(permissions.PAGE_KEYS) & OLD_KEYS)


# --- P11-c 판정 규칙 (DB 없이 판정 함수만 검증) ---

def test_no_account_no_access(monkeypatch):
    monkeypatch.setattr(ps, "is_super", lambda e: False)
    monkeypatch.setattr(ps, "perm_of", lambda e: None)
    assert permissions.allowed("x@a.com", None, "R") is False
    assert permissions.allowed("x@a.com", "dashboard", "R") is False


def test_super_allows_all(monkeypatch):
    monkeypatch.setattr(ps, "is_super", lambda e: True)
    monkeypatch.setattr(ps, "perm_of", lambda e: None)
    assert permissions.allowed("m@a.com", "workers", "D") is True


def test_grants_crud(monkeypatch):
    grants = {"worklogs": {"R": True, "C": True, "U": False, "D": False}}
    monkeypatch.setattr(ps, "is_super", lambda e: False)
    monkeypatch.setattr(ps, "perm_of", lambda e: grants)
    assert permissions.allowed("u@a.com", None, "R") is True
    assert permissions.allowed("u@a.com", "worklogs", "R") is True
    assert permissions.allowed("u@a.com", "worklogs", "C") is True
    assert permissions.allowed("u@a.com", "worklogs", "U") is False   # 마감 불가
    assert permissions.allowed("u@a.com", "vehicles", "R") is False
