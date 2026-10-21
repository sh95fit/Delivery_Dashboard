from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_email, is_admin_email
from app.services import control_exclude_service as svc

router = APIRouter(prefix="/control-excludes", tags=["control-excludes"])


class ExcludeIn(BaseModel):
    address_id: int
    label: Optional[str] = None
    memo: Optional[str] = None


def _admin(email: str = Depends(get_current_email)) -> str:
    if not is_admin_email(email):
        raise HTTPException(status_code=403, detail="관리자만 가능합니다")
    return email


@router.get("")
def list_excludes(_: str = Depends(get_current_email)):
    return {"items": svc.list_items()}


@router.post("")
def add_exclude(body: ExcludeIn, email: str = Depends(_admin)):
    try:
        return {"ok": True, "id": svc.add(body.address_id, body.label, body.memo, email)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{item_id}")
def delete_exclude(item_id: int, email: str = Depends(_admin)):
    try:
        svc.remove(item_id, email)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
