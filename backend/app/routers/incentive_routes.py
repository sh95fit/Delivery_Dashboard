from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_email
from app.schemas.incentive import IncentiveAll, IncentiveOne
from app.services import incentive_service

router = APIRouter(prefix="/incentive", tags=["incentive"])


@router.get("/{target_date}", response_model=IncentiveAll)
def get_incentive_all(
    target_date: date_type,
    _: str = Depends(get_current_email),
):
    try:
        return incentive_service.get_incentive_all(target_date)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"인센티브 조회 실패: {exc}") from exc


@router.get("/{target_date}/{manager_id}", response_model=IncentiveOne)
def get_incentive_one(
    target_date: date_type,
    manager_id: int,
    _: str = Depends(get_current_email),
):
    try:
        return incentive_service.get_incentive(target_date, manager_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"인센티브 조회 실패: {exc}") from exc
