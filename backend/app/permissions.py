"""P11-a 권한셋 중앙 제어 — 경로→(페이지, 연산) 매핑표 1곳 + 미들웨어.

- 권한셋 = 페이지별 R/C/U/D. 상위 제어(R) = 화면·데이터 열람, 하위 제어(C/U/D) = 기능·API
- 매핑 규칙 한 곳(이 파일)만 고치면 권한 규칙이 바뀐다 (엔드포인트 개별 수정 없음)
- 매핑에 없는 경로는 기본 차단 — 새 엔드포인트 추가 시 규칙 한 줄이 필수 (안전한 기본값)
"""
from __future__ import annotations

import os
import re

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.auth import deserialize_session

# (메서드, 경로 정규식, 페이지키, 연산) — 위에서부터 첫 matching rule이 이긴다.
# op None = 메서드에서 자동(POST=C PUT=U DELETE=D GET=R). page None = 로그인만 필요(공용).
RULES: list[tuple[str, re.Pattern, str | None, str | None]] = [
    # 공용 — 모든 로그인 사용자 (화면 진입점·기초데이터)
    ("GET",  re.compile(r"^/me$"), None, "R"),
    ("GET",  re.compile(r"^/admin$"), "settings", "R"),     # 허용목록 관리 페이지(자체 관리자 검사 유지)
    ("ANY",  re.compile(r"^/allowlist"), "settings", "U"),  # 허용목록 API — 현재 관리자 전용 유지
    ("GET",  re.compile(r"^/managers/?$"), None, "R"),
    ("GET",  re.compile(r"^/vehicles/?$"), None, "R"),
    # P11-b 계정·권한셋·초대 — require_super 전용 (미들웨어는 로그인만, 실제 권한은 deps.require_super)
    ("ANY",  re.compile(r"^/(accounts|permission-sets|invitations)"), None, "R"),    
    # 근무 기록 (내보내기·마감이 일반 근무 규칙보다 앞서야 함)
    ("GET",  re.compile(r"^/worklogs/export/plan"), "worklogs", "R"),   # 내보내기 옵션 조회 — 현재 열람 유지
    ("GET",  re.compile(r"^/worklogs/export$"), "worklog_export", "C"), # 실제 파일 생성 — 현재 관리자 전용 유지
    ("POST", re.compile(r"^/worklogs/close$"), "worklog_close", "C"),
    ("POST", re.compile(r"^/worklogs/reopen$"), "worklog_close", "U"),
    ("GET",  re.compile(r"^/worklogs"), "worklogs", "R"),
    ("ANY",  re.compile(r"^/worklogs"), "worklogs", None),
    # 인센티브 (단가·품목·특수수당 관리는 별도 페이지)
    ("GET",  re.compile(r"^/incentive/(rates|extra-items)"), "incentive_rates", "R"),
    ("POST|PUT|DELETE", re.compile(r"^/incentive/(rates|extra-items|extras)"), "incentive_rates", None),
    ("GET",  re.compile(r"^/incentive"), "incentive", "R"),
    ("ANY",  re.compile(r"^/incentive"), "incentive", None),
    # 물류비 (엑셀 내보내기는 현행대로 관리자 계열 — C)
    ("GET",  re.compile(r"^/logistics/export"), "logistics", "C"),
    ("ANY",  re.compile(r"^/logistics"), "logistics", None),
    # 차량·유류비 (유류비 엑셀 내보내기는 현재 열람 가능이라 R 유지)
    ("GET",  re.compile(r"^/fuel/export"), "fuel", "R"),
    ("ANY",  re.compile(r"^/vehicles"), "vehicles", None),
    ("ANY",  re.compile(r"^/fuel"), "fuel", None),
    # 인력·담당자 (엑셀 가져오기 계열은 현재 관리자 전용 유지)
    ("ANY",  re.compile(r"^/workers/import"), "workers", "C"),
    ("ANY",  re.compile(r"^/workers"), "workers", None),
    ("ANY",  re.compile(r"^/managers"), "managers", None),
    # 대시보드 부속 (관제 제외·현황·매출)
    ("ANY",  re.compile(r"^/control-excludes"), "dashboard", None),
    ("GET",  re.compile(r"^/(status|deliveries|revenue)"), "dashboard", "R"),
    # 직원식 — 별도 페이지키 (사용자 확정). 검색은 현재 관리자 전용 유지
    ("GET",  re.compile(r"^/internal-targets/search"), "internal", "C"),
    ("ANY",  re.compile(r"^/internal-targets"), "internal", None),
    # 경로 — 조회·미리보기는 현행대로 열람(대시보드 계산 버튼이 비관리자에게도 열려 있었음), 강제 갱신만 C
    ("POST", re.compile(r"^/routes/[^/]+/refresh"), "routes", "C"),
    ("POST", re.compile(r"^/routes/.*preview"), "routes", "R"),   # {일}/preview-all · {일}/{매니저}/preview 전부
    ("ANY",  re.compile(r"^/routes"), "routes", None),
]
EXEMPT = re.compile(r"^/(health|health/db|auth/login|auth/callback|auth/logout|docs|openapi.json|redoc)(/|$)")
OP_OF = {"POST": "C", "PUT": "U", "DELETE": "D", "PATCH": "U", "GET": "R"}


def resolve(path: str, method: str) -> tuple[str | None, str | None]:
    """경로·메서드 → (페이지키, 연산). 매칭 없음 = (None, None) = 기본 차단."""
    if path.startswith("/api/"):
        path = path[4:]
    for m, pat, page, op in RULES:
        if (m == "ANY" or method in m.split("|")) and pat.search(path):
            return page, op or OP_OF.get(method, "R")
    return None, None


def allowed(email: str, page: str | None, op: str | None) -> bool:
    from app.services import permission_service as ps
    if page is None:                        # 공용 경로 (로그인만 필요)
        return True
    if ps.is_super(email):                  # 시스템 어드민 = 전체 허용
        return True
    g = ps.perm_of(email)
    if g is None:
        # [P11-a 폴백] 계정 미생성(이관 전) 사용자: 기존 동작 유지 — 읽기 허용·쓰기 차단.
        # P11-b에서 계정·권한셋 배정으로 정리되면 이 분기는 사실상 사라진다.
        return (op or "R") == "R"
    return bool((g.get(page) or {}).get(op or "R"))


class PermissionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/"):
            path = path[4:]
        if EXEMPT.search(path):
            return await call_next(request)

        # 신원 확인 (auth.get_current_email과 같은 규칙: 내부 토큰 → 세션 쿠키)
        email = None
        tok = os.environ.get("INTERNAL_API_TOKEN", "").strip()
        if tok and (request.headers.get("X-Internal-Token") or "").strip() == tok:
            email = "internal@lunchlab.me"
        else:
            raw = request.cookies.get("lunchlab_session")
            email = deserialize_session(raw) if raw else None
        if not email:
            return JSONResponse({"detail": "로그인이 필요합니다"}, status_code=401)

        page, op = resolve(request.url.path, request.method)
        if page is None and op is None:
            return JSONResponse({"detail": "권한 설정이 없는 경로입니다 — 관리자에게 문의하세요"},
                                status_code=403)
        if not allowed(email, page, op):
            return JSONResponse({"detail": "권한이 없습니다"}, status_code=403)
        return await call_next(request)
