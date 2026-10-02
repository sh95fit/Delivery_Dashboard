from fastapi import APIRouter, Depends

from app.auth import get_current_email
from app.deps import guard, memo, require_admin
from app.schemas.masters import AssignIn, PayRateIn, ProfileIn
from app.services import dash_db
from app.services import manager_service as svc

router = APIRouter(prefix="/managers", tags=["managers"])


@router.get("")
def list_managers(_: str = Depends(get_current_email)):
    return {"items": guard(svc.list_managers, fail="매니저 조회 실패")}


@router.get("/{mid}")
def manager_detail(mid: int, _: str = Depends(get_current_email)):
    return guard(svc.manager_detail, mid, fail="매니저 상세 조회 실패")


@router.put("/{mid}/profile")
def save_profile(mid: int, body: ProfileIn, email: str = Depends(require_admin)):
    guard(svc.save_profile, mid, body.active, memo(body.memo), email, fail="저장 실패")
    return {"ok": True}


@router.post("/{mid}/rates")
def add_rate(mid: int, body: PayRateIn, email: str = Depends(require_admin)):
    new_id = guard(svc.add_rate, mid, body.pay_type, body.amount, body.effective_from, memo(body.memo), email,
                   fail="급여 저장 실패")
    return {"ok": True, "id": new_id}


@router.delete("/rates/{rid}")
def delete_rate(rid: int, email: str = Depends(require_admin)):
    guard(dash_db.soft_delete, "manager_pay_rates", rid, email, fail="삭제 실패")
    return {"ok": True}


@router.post("/{mid}/vehicle")
def assign_vehicle(mid: int, body: AssignIn, email: str = Depends(require_admin)):
    new_id = guard(svc.assign_vehicle, mid, body.vehicle_id, body.start_date, email, fail="차량 배정 실패")
    return {"ok": True, "id": new_id}


@router.delete("/assignments/{aid}")
def delete_assignment(aid: int, email: str = Depends(require_admin)):
    guard(dash_db.soft_delete, "vehicle_assignments", aid, email, fail="삭제 실패")
    return {"ok": True}
