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


class RuleBody(BaseModel):
    kind: str
    value: str
    permission_set_id: int
    active: bool = True
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


@router.get("/access-rules")
def list_rules():
    return guard(svc.list_rules, fail="접근 규칙 조회 실패")


@router.post("/access-rules")
def create_rule(b: RuleBody, email: str = Depends(require_super)):
    return guard(svc.create_rule, b.kind, b.value, b.permission_set_id, b.active, b.memo, email,
                 fail="접근 규칙 생성 실패")


@router.put("/access-rules/{rule_id}")
def update_rule(rule_id: int, b: RuleBody, email: str = Depends(require_super)):
    return guard(svc.update_rule, rule_id, b.kind, b.value, b.permission_set_id, b.active,
                 b.memo, email, fail="접근 규칙 수정 실패")


@router.delete("/access-rules/{rule_id}")
def delete_rule(rule_id: int, email: str = Depends(require_super)):
    return guard(svc.delete_rule, rule_id, email, fail="접근 규칙 삭제 실패")
