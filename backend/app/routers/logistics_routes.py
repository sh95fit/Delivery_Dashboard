from datetime import date

from fastapi import APIRouter, Depends, Query

from app.auth import get_current_email
from app.deps import guard, memo, require_admin
from app.schemas.masters import DayOverrideIn
from app.services import calendar_service as cal
from app.services import logistics_service as svc
from app.services import logistics_export
from app.services.excel_export import xlsx_response

router = APIRouter(prefix="/logistics", tags=["logistics"])


@router.get("/cost")
def cost(frm: date = Query(..., alias="from"), to: date = Query(...), _: str = Depends(require_admin)):
    return guard(svc.cost_view, frm, to, fail="물류비 조회 실패")


@router.get("/business-days")
def get_business_days(frm: date = Query(..., alias="from"), to: date = Query(...),
                      _: str = Depends(get_current_email)):
    return guard(cal.day_list, frm, to, fail="영업일 조회 실패")


@router.put("/business-days/{d}")
def set_business_day(d: date, body: DayOverrideIn, email: str = Depends(require_admin)):
    new_id = guard(cal.set_override, d, body.is_open, memo(body.memo), email, fail="영업일 지정 실패")
    return {"ok": True, "id": new_id}


@router.delete("/business-days/{d}")
def clear_business_day(d: date, email: str = Depends(require_admin)):
    guard(cal.clear_override, d, email, fail="영업일 지정 해제 실패")
    return {"ok": True}


@router.get("/export")
def export_cost(frm: date = Query(..., alias="from"), to: date = Query(...), _: str = Depends(require_admin)):
    name, sheets = guard(logistics_export.cost_sheets, frm, to, fail="물류비 내보내기 실패")
    return xlsx_response(name, sheets)