from datetime import date
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response

from app.auth import get_current_email
from app.deps import guard, memo, require_admin
from app.schemas.worklogs import WorkDayIn, WorkPersonIn
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


@router.put("/person/{wid}")
def save_person(wid: int, body: WorkPersonIn, email: str = Depends(require_admin)):
    items = [i.model_dump() for i in body.items]
    for i in items:
        i["memo"] = memo(i.get("memo"))
    return guard(svc.save_person, wid, items, body.delete_ids, email, fail="근무 기록 저장 실패")


@router.delete("/{lid}")
def delete_log(lid: int, email: str = Depends(require_admin)):
    guard(svc.delete_log, lid, email, fail="근무 기록 삭제 실패")
    return {"ok": True}


@router.get("/export/plan")
def export_plan(month: date = Query(...), start: date | None = Query(None), end: date | None = Query(None),
                ids: list[int] | None = Query(None), _: str = Depends(get_current_email)):
    return guard(svc.export_plan, month, start, end, ids, fail="근무표 점검 실패")


@router.get("/export")
def export_file(sheet: Literal["labor", "business", "all"] = Query(...), month: date = Query(...),
                start: date | None = Query(None), end: date | None = Query(None),
                ids: list[int] | None = Query(None), _: str = Depends(require_admin)):
    name, data, media = guard(svc.export_file, sheet, month, start, end, ids, fail="근무표 생성 실패")
    ext = name.rsplit(".", 1)[-1]
    return Response(content=data, media_type=media, headers={
        "Content-Disposition": f"attachment; filename=\"timesheet.{ext}\"; filename*=UTF-8''{quote(name)}"})
