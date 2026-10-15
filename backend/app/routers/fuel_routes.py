from datetime import date

from fastapi import APIRouter, Depends, Query

from app.auth import get_current_email
from app.deps import guard, memo, require_admin
from app.schemas.masters import FuelPriceIn
from app.services import fuel_price_service as svc

router = APIRouter(prefix="/fuel", tags=["fuel"])


@router.get("/prices")
def prices(frm: date = Query(..., alias="from"), to: date = Query(...), _: str = Depends(get_current_email)):
    return guard(svc.list_prices, frm, to, fail="유가 조회 실패")


@router.post("/prices")
def add_price(body: FuelPriceIn, email: str = Depends(require_admin)):
    new_id = guard(svc.add_manual, body.price_date, body.fuel_type, body.price, memo(body.memo), email,
                   fail="단가 저장 실패")
    return {"ok": True, "id": new_id}


@router.delete("/prices/{pid}")
def delete_price(pid: int, email: str = Depends(require_admin)):
    guard(svc.delete_manual, pid, email, fail="단가 삭제 실패")
    return {"ok": True}


@router.post("/prices/fetch")
def fetch_now(_: str = Depends(require_admin)):
    return {"ok": True, "saved": guard(svc.fetch_opinet, fail="오피넷 수집 실패")}
