"""P11 Step3-2 권한셋·접근규칙 API — 시스템 어드민(마스터) 전용."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.deps import guard, require_super
from app.services import permission_admin_service as svc

# 라우터 전체에 require_super (2중 방어) + 각 엔드포인트에서 이메일을 받아 기록용으로 사용
router = APIRouter(tags=["permission-admin"], dependencies=[Depends(require_super)])


class SetBody(BaseModel):
    name: str
    grants: dict = {}
    memo: str | None = None


@router.get("/permission-sets")
def list_sets():
    return guard(svc.list_sets, fail="권한셋 조회 실패")


@router.post("/permission-sets")
def create_set(b: SetBody, email: str = Depends(require_super)):
    return guard(svc.create_set, b.name, b.grants, b.memo, email, fail="권한셋 생성 실패")


@router.put("/permission-sets/{set_id}")
def update_set(set_id: int, b: SetBody, email: str = Depends(require_super)):
    return guard(svc.update_set, set_id, b.name, b.grants, b.memo, email, fail="권한셋 수정 실패")


@router.delete("/permission-sets/{set_id}")
def delete_set(set_id: int, email: str = Depends(require_super)):
    return guard(svc.delete_set, set_id, email, fail="권한셋 삭제 실패")
