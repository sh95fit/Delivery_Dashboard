from fastapi import APIRouter, Depends

from app.auth import get_current_email
from app.deps import guard, memo, require_admin
from app.schemas.masters import ProfileIn
from app.services import manager_service as svc

# [S3-P2h-3a] 계정 = 운영 배송 기록 단위. 급여는 인력 계약 조건, 차량은 인력 차량 이용 → 계정 급여·차량 배정 API 삭제
router = APIRouter(prefix="/managers", tags=["managers"])


@router.get("")
def list_managers(_: str = Depends(get_current_email)):
    return {"items": guard(svc.list_managers, fail="매니저 조회 실패")}


@router.put("/{mid}/profile")
def save_profile(mid: int, body: ProfileIn, email: str = Depends(require_admin)):
    guard(svc.save_profile, mid, body.active, memo(body.memo), email, fail="저장 실패")
    return {"ok": True}
