from datetime import date

from fastapi import APIRouter, Depends, Query

from app.auth import get_current_email
from app.deps import guard, memo, require_admin
from app.schemas.masters import ExpenseIn, PeriodCostIn, VehicleIn
from app.services import dash_db
from app.services import vehicle_service as svc

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


@router.get("")
def list_vehicles(_: str = Depends(get_current_email)):
    return {"items": guard(svc.list_vehicles, fail="차량 조회 실패")}


@router.post("")
def create_vehicle(body: VehicleIn, email: str = Depends(require_admin)):
    return {"ok": True, "id": guard(svc.create_vehicle, svc.vehicle_dict(body), email, fail="차량 등록 실패")}


@router.put("/{vid}")
def update_vehicle(vid: int, body: VehicleIn, email: str = Depends(require_admin)):
    guard(svc.update_vehicle, vid, svc.vehicle_dict(body), email, fail="차량 수정 실패")
    return {"ok": True}


@router.delete("/{vid}")
def delete_vehicle(vid: int, email: str = Depends(require_admin)):
    guard(dash_db.soft_delete, "vehicles", vid, email, fail="차량 삭제 실패")
    return {"ok": True}


@router.get("/period-costs")
def list_period_costs(vehicle_id: int | None = None, _: str = Depends(get_current_email)):
    return {"items": guard(svc.list_period_costs, vehicle_id, fail="기간 비용 조회 실패")}


@router.post("/period-costs")
def add_period_cost(body: PeriodCostIn, email: str = Depends(require_admin)):
    new_id = guard(svc.add_period_cost, body.vehicle_id, body.category, body.amount, body.start_date,
                   body.end_date, memo(body.memo), email, fail="기간 비용 저장 실패")
    return {"ok": True, "id": new_id}


@router.delete("/period-costs/{pid}")
def delete_period_cost(pid: int, email: str = Depends(require_admin)):
    guard(dash_db.soft_delete, "vehicle_period_costs", pid, email, fail="삭제 실패")
    return {"ok": True}


@router.get("/expenses")
def list_expenses(frm: date = Query(..., alias="from"), to: date = Query(...),
                  vehicle_id: int | None = None, _: str = Depends(get_current_email)):
    return {"items": guard(svc.list_expenses, frm, to, vehicle_id, fail="지출 조회 실패")}


@router.post("/expenses")
def add_expense(body: ExpenseIn, email: str = Depends(require_admin)):
    new_id = guard(svc.add_expense, body.vehicle_id, body.expense_date, body.category, body.amount,
                   memo(body.memo), email, fail="지출 저장 실패")
    return {"ok": True, "id": new_id}


@router.delete("/expenses/{eid}")
def delete_expense(eid: int, email: str = Depends(require_admin)):
    guard(dash_db.soft_delete, "vehicle_expenses", eid, email, fail="삭제 실패")
    return {"ok": True}


@router.get("/cost-summary")
def cost_summary(frm: date = Query(..., alias="from"), to: date = Query(...),
                 _: str = Depends(get_current_email)):
    return guard(svc.cost_summary, frm, to, fail="비용 요약 실패")
