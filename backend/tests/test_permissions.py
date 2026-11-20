from app.permissions import resolve


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
    assert resolve("/admin", "GET") == ("settings", "R")     # 허용목록 페이지
    assert resolve("/allowlist", "GET") == ("settings", "U")   # 현재 관리자 전용 유지
    assert resolve("/allowlist", "POST") == ("settings", "U")
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
