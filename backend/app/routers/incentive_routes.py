from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_email, is_admin_email
from app.schemas.incentive import AdjustRequest, HoldRequest, IncentiveAll, IncentiveOne
from app.services import incentive_service

router = APIRouter(prefix="/incentive", tags=["incentive"])


@router.get("/{target_date}", response_model=IncentiveAll)
def get_incentive_all(target_date: date_type, _: str = Depends(get_current_email)):
    try:
        return incentive_service.get_incentive_all(target_date)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"인센티브 조회 실패: {exc}") from exc


@router.get("/{target_date}/{manager_id}", response_model=IncentiveOne)
def get_incentive_one(target_date: date_type, manager_id: int,
                      _: str = Depends(get_current_email)):
    try:
        return incentive_service.get_incentive(target_date, manager_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"인센티브 조회 실패: {exc}") from exc


@router.post("/{target_date}/{manager_id}/adjust")
def adjust_incentive(target_date: date_type, manager_id: int, body: AdjustRequest,
                     email: str = Depends(get_current_email)):
    if not is_admin_email(email):
        raise HTTPException(status_code=403, detail="관리자만 가능합니다")
    try:
        incentive_service.set_adjustment(target_date, manager_id, body.field,
                                         body.value, body.reason, email)
        return {"ok": True, "manager_id": manager_id,
                "date": target_date.isoformat(), "field": body.field, "value": body.value}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"조정 실패: {exc}") from exc


@router.post("/{target_date}/{manager_id}/hold")
def hold_incentive(target_date: date_type, manager_id: int, body: HoldRequest,
                   email: str = Depends(get_current_email)):
    if not is_admin_email(email):
        raise HTTPException(status_code=403, detail="관리자만 가능합니다")
    try:
        incentive_service.set_hold(target_date, manager_id, body.reason, email)
        return {"ok": True, "manager_id": manager_id,
                "date": target_date.isoformat(), "is_held": True, "reason": body.reason}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"미지급 처리 실패: {exc}") from exc


@router.delete("/{target_date}/{manager_id}/hold")
def release_incentive(target_date: date_type, manager_id: int,
                      email: str = Depends(get_current_email)):
    if not is_admin_email(email):
        raise HTTPException(status_code=403, detail="관리자만 가능합니다")
    try:
        incentive_service.release_hold(target_date, manager_id)
        return {"ok": True, "manager_id": manager_id,
                "date": target_date.isoformat(), "is_held": False}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"미지급 해제 실패: {exc}") from exc
