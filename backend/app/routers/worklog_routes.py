from datetime import date

from fastapi import APIRouter, Depends, Query

from app.auth import get_current_email
from app.deps import guard, memo, require_admin
from app.schemas.worklogs import WorkDayIn
from app.services import worklog_service as svc

router = APIRouter(prefix="/worklogs", tags=["worklogs"])


@router.get("/month")
def month_view(month: date = Query(..., description="그 달 아무 날짜 (예: 2026-10-01)"),
               _: str = Depends(get_current_email)):
    return guard(svc.month_view, month, fail="월 근무 기록 조회 실패")


@router.get("/day")
def day_view(d: date = Query(...), _: str = Depends(get_current_email)):
    return guard(svc.day_view, d, fail="일일 근무 기록 조회 실패")


@router.put("/day/{d}")
def save_day(d: date, body: WorkDayIn, email: str = Depends(require_admin)):
    items = [i.model_dump() for i in body.items]
    for i in items:
        i["memo"] = memo(i.get("memo"))
    return guard(svc.save_day, d, items, email, fail="근무 기록 저장 실패")


@router.delete("/{lid}")
def delete_log(lid: int, email: str = Depends(require_admin)):
    guard(svc.delete_log, lid, email, fail="근무 기록 삭제 실패")
    return {"ok": True}
