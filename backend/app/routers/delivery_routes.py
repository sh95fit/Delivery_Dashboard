from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_email
from app.schemas.delivery import DeliveryDayResponse
from app.services import delivery_service

router = APIRouter(prefix="/deliveries", tags=["deliveries"])


@router.get("/{target_date}", response_model=DeliveryDayResponse)
def get_deliveries(
    target_date: date_type,
    _: str = Depends(get_current_email),
):
    try:
        return delivery_service.get_delivery_day(target_date)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"배송현황 조회 실패: {exc}") from exc
