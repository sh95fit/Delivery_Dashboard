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


# 공식 페이지키 — 권한셋 grants·프론트 nav.ts·관리 API 검증이 모두 이 목록을 따른다
PAGE_KEYS: tuple[str, ...] = (
    "dashboard", "worklogs", "incentive", "logistics", "vehicles",
    "workers", "managers", "internal",
    "packing", "sales", "analysis", "simulation",   # 준비중 화면 (040)
)


# (메서드, 경로 정규식, 페이지키, 연산) — 위에서부터 첫 matching rule이 이긴다.
# op None = 메서드에서 자동(POST=C PUT=U DELETE=D GET=R). page None = 로그인만 필요(공용).
RULES: list[tuple[str, re.Pattern, str | None, str | None]] = [
    # 공용 — 모든 로그인 사용자 (화면 진입점·기초데이터)
    ("GET",  re.compile(r"^/me$"), None, "R"),
    ("GET",  re.compile(r"^/managers/?$"), None, "R"),
    ("GET",  re.compile(r"^/vehicles/?$"), None, "R"),
    # 계정·권한셋·규칙·초대 — 미들웨어는 로그인만, 실제 권한은 deps.require_super
    ("ANY",  re.compile(r"^/(permission-sets|users)"), None, "R"),
    # 근무 기록 — 마감/재오픈 = U, 내보내기 = R (일반 근무 규칙보다 앞서야 함)
    ("GET",  re.compile(r"^/worklogs/export"), "worklogs", "R"),
    ("POST", re.compile(r"^/worklogs/(close|reopen)$"), "worklogs", "U"),
    ("GET",  re.compile(r"^/worklogs"), "worklogs", "R"),
    ("ANY",  re.compile(r"^/worklogs"), "worklogs", None),
    # 인센티브 — 단가·품목·특수수당 조회 = R, 변경 = U
    ("GET",  re.compile(r"^/incentive/(rates|extra-items)"), "incentive", "R"),
    ("POST|PUT|DELETE", re.compile(r"^/incentive/(rates|extra-items|extras)"), "incentive", "U"),
    ("GET",  re.compile(r"^/incentive"), "incentive", "R"),
    ("ANY",  re.compile(r"^/incentive"), "incentive", None),
    # 물류비 (엑셀 내보내기는 관리자 계열 — C)
    ("GET",  re.compile(r"^/logistics/export"), "logistics", "C"),
    ("ANY",  re.compile(r"^/logistics"), "logistics", None),
    # 차량·유류비 — 유류비는 차량 권한으로 통합 (내보내기 = R)
    ("GET",  re.compile(r"^/fuel/export"), "vehicles", "R"),
    ("ANY",  re.compile(r"^/vehicles"), "vehicles", None),
    ("ANY",  re.compile(r"^/fuel"), "vehicles", None),
    # 인력·담당자 (엑셀 가져오기는 C)
    ("ANY",  re.compile(r"^/workers/import"), "workers", "C"),
    ("ANY",  re.compile(r"^/workers"), "workers", None),
    ("ANY",  re.compile(r"^/managers"), "managers", None),
    # 대시보드 부속 (관제 제외·현황·매출)
    ("ANY",  re.compile(r"^/control-excludes"), "dashboard", None),
    ("GET",  re.compile(r"^/(status|deliveries|revenue)"), "dashboard", "R"),
    # 직원식 — 검색은 C
    ("GET",  re.compile(r"^/internal-targets/search"), "internal", "C"),
    ("ANY",  re.compile(r"^/internal-targets"), "internal", None),
    # 경로 → 대시보드 권한으로 통합 — 미리보기 = R, 강제 갱신 = C
    ("POST", re.compile(r"^/routes/[^/]+/refresh"), "dashboard", "C"),
    ("POST", re.compile(r"^/routes/.*preview"), "dashboard", "R"),
    ("ANY",  re.compile(r"^/routes"), "dashboard", None),
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
    """P11-c 판정: 마스터 전체 허용 → 규칙 권한셋 → 없으면 차단(폴백 없음)."""
    from app.services import permission_service as ps
    if ps.is_super(email):
        return True
    grants = ps.perm_of(email)
    if grants is None:
        return False
    if page is None:          # 공용 경로 — 권한셋이 있는 로그인 사용자면 허용
        return True
    return bool((grants.get(page) or {}).get(op or "R"))


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
