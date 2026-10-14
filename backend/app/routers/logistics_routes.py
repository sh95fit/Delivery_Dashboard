from datetime import date

from fastapi import APIRouter, Depends, Query

from app.deps import guard, require_admin
from app.services import logistics_service as svc

router = APIRouter(prefix="/logistics", tags=["logistics"])


@router.get("/cost")
def cost(frm: date = Query(..., alias="from"), to: date = Query(...), _: str = Depends(require_admin)):
    return guard(svc.cost_view, frm, to, fail="물류비 조회 실패")
