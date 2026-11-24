from app import permissions
from app.permissions import resolve
from app.services import permission_service as ps


def test_write_ops_map_to_page():
    assert resolve("/worklogs/day/2026-10-01", "PUT") == ("worklogs", "U")
    assert resolve("/fuel/logs", "POST") == ("fuel", "C")
    assert resolve("/workers/rates/5", "DELETE") == ("workers", "D")


def test_special_pages():
    assert resolve("/worklogs/close", "POST") == ("worklog_close", "C")
    assert resolve("/worklogs/reopen", "POST") == ("worklog_close", "U")
    assert resolve("/worklogs/export", "GET") == ("worklog_export", "C")
    assert resolve("/incentive/rates", "POST") == ("incentive_rates", "C")


def test_login_only_and_unmapped():
    assert resolve("/me", "GET") == (None, "R")              # 공용 진입점
    assert resolve("/managers", "GET")[0] is None            # 공용 기초데이터
    assert resolve("/vehicles", "GET")[0] is None
    assert resolve("/admin", "GET") == (None, None)          # P11-c 허용목록 페이지 제거 → 기본 차단
    assert resolve("/allowlist", "GET") == (None, None)      # P11-c 허용목록 API 제거 → 기본 차단
    assert resolve("/internal-targets", "POST") == ("internal", "C")   # 직원식 = 별도 페이지
    assert resolve("/internal-targets/search", "GET") == ("internal", "C")
    assert resolve("/routes/2026-11-19/7/preview", "POST") == ("routes", "R")    # 미리보기 현행 유지
    assert resolve("/routes/2026-11-19/preview-all", "POST") == ("routes", "R")
    assert resolve("/logistics/export", "GET") == ("logistics", "C")  # 내보내기 현행(관리자) 유지
    assert resolve("/fuel/export", "GET") == ("fuel", "R")            # 유류비 내보내기 현행(열람) 유지
    assert resolve("/workers/import/accounts", "GET") == ("workers", "C")
    assert resolve("/worklogs/export/plan", "GET") == ("worklogs", "R")
    assert resolve("/worklogs/export", "GET") == ("worklog_export", "C")
    assert resolve("/nonsense", "GET") == (None, None)       # 기본 차단


def test_api_prefix_and_order():
    assert resolve("/api/fuel/logs", "POST") == ("fuel", "C")
    assert resolve("/worklogs/close/check", "GET") == ("worklogs", "R")   # 마감 조회는 근무 열람


# --- P11-c 판정 규칙 (DB 없이 판정 함수만 검증) ---

def test_no_account_no_access(monkeypatch):
    """규칙·계정이 없으면 공용 경로(/me)조차 차단 — '열람' 폴백 금지."""
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
    assert permissions.allowed("u@a.com", None, "R") is True           # 공용 경로
    assert permissions.allowed("u@a.com", "worklogs", "R") is True
    assert permissions.allowed("u@a.com", "worklogs", "C") is True
    assert permissions.allowed("u@a.com", "worklogs", "U") is False
    assert permissions.allowed("u@a.com", "fuel", "R") is False        # 권한셋에 없는 화면 = 차단
