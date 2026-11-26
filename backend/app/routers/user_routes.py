"""P11 Step3-4 사용자 API (규칙+계정+초대 통합) — 마스터 전용.
Step3-5: 초대 메일 발송(최초·재발송)은 서비스에서 검증·제한(429) 후 발송 결과를 기록한다."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.deps import guard, require_super
from app.services import mail_service
from app.services import user_service as svc

router = APIRouter(tags=["users"], dependencies=[Depends(require_super)])

_NO_MAIL = "메일 설정(GMAIL_USER/GMAIL_APP_PASSWORD)이 없습니다"


class UserBody(BaseModel):
    email: str
    permission_set_id: int
    days: int | None = 7
    memo: str | None = None


class PermSetBody(BaseModel):
    permission_set_id: int


class ActiveBody(BaseModel):
    active: bool


def _send(r: dict) -> dict:
    mail = mail_service.send_invite(r["email"], r["days"])
    svc.finish_send(r["send_id"], mail)
    return {"email": r["email"], **mail, "counted": True}


@router.get("/users")
def list_users(me: str = Depends(require_super)):
    return guard(svc.list_users, me, fail="사용자 조회 실패")


@router.post("/users")
def create_user(b: UserBody, me: str = Depends(require_super)):
    ready = svc.mail_ready()      # 메일 설정이 없으면 초대만 저장하고 발송 횟수는 세지 않음
    r = guard(svc.create_user, b.email, b.permission_set_id, b.days, b.memo, me, ready, fail="초대 실패")
    if not ready:
        return {"email": r["email"], "mail_sent": False, "mail_error": _NO_MAIL, "counted": False}
    return _send(r)


@router.post("/users/{email}/invitation/resend")
def resend_invite(email: str, me: str = Depends(require_super)):
    # 유효기간은 클라이언트 값 대신 서버의 expires_at으로 계산 (만료일은 바꾸지 않음)
    return _send(guard(svc.prepare_resend, email, me, fail="재발송 실패"))


@router.put("/users/{email}/permission-set")
def set_permission_set(email: str, b: PermSetBody):
    return guard(svc.set_permission_set, email, b.permission_set_id, fail="권한셋 변경 실패")


@router.put("/users/{email}/active")
def set_active(email: str, b: ActiveBody, me: str = Depends(require_super)):
    return guard(svc.set_active, email, b.active, me, fail="상태 변경 실패")


@router.delete("/users/{email}/invitation")
def revoke_invite(email: str, me: str = Depends(require_super)):
    return guard(svc.revoke_invite, email, me, fail="초대 취소 실패")


@router.delete("/users/{email}")
def delete_user(email: str, me: str = Depends(require_super)):
    return guard(svc.delete_user, email, me, fail="삭제 실패")
