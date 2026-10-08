def test_app_starts_with_worklog_routes():
    """라우터·스키마 import 오류(빈 파일 등)는 문법 검사로 못 잡음 → 앱을 불러와 OpenAPI 경로로 확인.
    app.routes 내부 구조는 FastAPI 버전마다 달라서 쓰지 않음"""
    from app.main import app
    paths = set(app.openapi()["paths"])
    assert {"/worklogs/day", "/worklogs/month", "/worklogs/day/{d}", "/worklogs/{lid}",
            "/worklogs/export", "/worklogs/export/plan"} <= paths
