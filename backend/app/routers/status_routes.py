from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_email
from app.schemas.status import DeliveryStatusResponse
from app.services import status_service

router = APIRouter(prefix="/status", tags=["status"])


@router.get("/{target_date}", response_model=DeliveryStatusResponse)
def get_status(
    target_date: date_type,
    _: str = Depends(get_current_email),
):
    try:
        return status_service.get_status(target_date)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"상태 조회 실패: {exc}") from exc
