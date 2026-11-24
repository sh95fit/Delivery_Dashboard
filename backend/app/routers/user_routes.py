"""P11 Step3-4 사용자 API (규칙+계정+초대 통합) — 마스터 전용."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.deps import guard, require_super
from app.services import mail_service
from app.services import user_service as svc

router = APIRouter(tags=["users"], dependencies=[Depends(require_super)])


class UserBody(BaseModel):
    email: str
    permission_set_id: int
    days: int | None = 7
    memo: str | None = None


class PermSetBody(BaseModel):
    permission_set_id: int


class ActiveBody(BaseModel):
    active: bool


@router.get("/users")
def list_users(me: str = Depends(require_super)):
    return guard(svc.list_users, me, fail="사용자 조회 실패")


@router.post("/users")
def create_user(b: UserBody, me: str = Depends(require_super)):
    r = guard(svc.create_user, b.email, b.permission_set_id, b.days, b.memo, me, fail="초대 실패")
    return {**r, **mail_service.send_invite(r["email"], b.days or 7)}


class ResendBody(BaseModel):
    days: int = 7


@router.post("/users/{email}/invitation/resend")
def resend_invite(email: str, b: ResendBody):
    return mail_service.send_invite(email.strip().lower(), b.days)


@router.put("/users/{email}/permission-set")
def set_permission_set(email: str, b: PermSetBody):
    return guard(svc.set_permission_set, email, b.permission_set_id, fail="권한셋 변경 실패")


@router.put("/users/{email}/active")
def set_active(email: str, b: ActiveBody, me: str = Depends(require_super)):
    return guard(svc.set_active, email, b.active, me, fail="상태 변경 실패")


@router.delete("/users/{email}/invitation")
def revoke_invite(email: str, me: str = Depends(require_super)):
    return guard(svc.revoke_invite, email, me, fail="초대 취소 실패")
