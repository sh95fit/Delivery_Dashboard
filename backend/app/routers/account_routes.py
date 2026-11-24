"""P11 Step3-3 계정·초대 API — 시스템 어드민(마스터) 전용."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.deps import guard, require_super
from app.services import account_service as svc

router = APIRouter(tags=["accounts"], dependencies=[Depends(require_super)])


class InviteBody(BaseModel):
    email: str
    days: int | None = 7
    memo: str | None = None


class ActiveBody(BaseModel):
    active: bool


@router.get("/accounts")
def list_accounts():
    return guard(svc.list_accounts, fail="계정 조회 실패")


@router.put("/accounts/{acc_id}/active")
def set_active(acc_id: int, b: ActiveBody, email: str = Depends(require_super)):
    return guard(svc.set_account_active, acc_id, b.active, email, fail="계정 상태 변경 실패")


@router.get("/invitations")
def list_invitations():
    return guard(svc.list_invitations, fail="초대 조회 실패")


@router.post("/invitations")
def create_invitation(b: InviteBody, email: str = Depends(require_super)):
    return guard(svc.create_invitation, b.email, b.days, b.memo, email, fail="초대 등록 실패")


@router.delete("/invitations/{inv_id}")
def revoke_invitation(inv_id: int, email: str = Depends(require_super)):
    return guard(svc.revoke_invitation, inv_id, email, fail="초대 취소 실패")
