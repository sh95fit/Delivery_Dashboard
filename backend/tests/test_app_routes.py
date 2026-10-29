def test_app_starts_with_worklog_routes():
    """라우터·스키마 import 오류(빈 파일 등)는 문법 검사로 못 잡음 → 앱을 불러와 OpenAPI 경로로 확인.
    app.routes 내부 구조는 FastAPI 버전마다 달라서 쓰지 않음"""
    from app.main import app
    paths = set(app.openapi()["paths"])
    assert {"/worklogs/day", "/worklogs/month", "/worklogs/day/{d}", "/worklogs/{lid}",
            "/worklogs/export", "/worklogs/export/plan", "/worklogs/offs/{d}",
            "/worklogs/close/check", "/worklogs/close", "/worklogs/reopen"} <= paths


def test_app_starts_with_incentive_routes():
    from app.main import app
    paths = set(app.openapi()["paths"])
    assert {"/incentive/day", "/incentive/month", "/incentive/rates", "/incentive/accounts/{d}",
            "/incentive/exclusions", "/incentive/extras", "/incentive/extra-items",
            "/incentive/holds/{d}", "/incentive/holds/{hid}/release"} <= paths


def test_manager_pay_vehicle_routes_removed():
    """[S3-P2h-3a] 계정에는 급여·차량을 저장하지 않음 (인력 계약 조건 · 인력 차량 이용으로 일원화)"""
    from app.main import app
    paths = set(app.openapi()["paths"])
    assert {"/managers", "/managers/{mid}/profile"} <= paths
    assert not {"/managers/{mid}", "/managers/{mid}/rates", "/managers/rates/{rid}",
                "/managers/{mid}/vehicle", "/managers/assignments/{aid}"} & paths
