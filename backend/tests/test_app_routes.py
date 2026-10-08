def test_app_starts_with_worklog_routes():
    """라우터·스키마 import 오류(빈 파일 등)는 문법 검사로 못 잡음 → 앱을 실제로 불러와 확인"""
    from app.main import app
    paths = {r.path for r in app.routes}
    assert {"/worklogs/day", "/worklogs/month", "/worklogs/day/{d}"} <= paths
