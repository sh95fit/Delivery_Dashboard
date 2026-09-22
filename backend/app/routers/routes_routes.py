from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_email, is_admin_email
from app.services import routes_service

router = APIRouter(prefix="/routes", tags=["routes"])


@router.get("/{target_date}")
def get_all_routes(target_date: date_type, _: str = Depends(get_current_email)):
    try:
        return routes_service.get_routes(target_date)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"전체 경로 조회 실패: {exc}") from exc


@router.get("/{target_date}/{manager_id}")
def get_route(target_date: date_type, manager_id: int,
              _: str = Depends(get_current_email)):
    try:
        return routes_service.get_route(target_date, manager_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"경로 조회 실패: {exc}") from exc


@router.post("/{target_date}/{manager_id}/refresh")
def refresh_route(target_date: date_type, manager_id: int,
                  email: str = Depends(get_current_email)):
    if not is_admin_email(email):
        raise HTTPException(status_code=403, detail="관리자만 가능합니다")
    try:
        return routes_service.force_refresh(target_date, manager_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"경로 갱신 실패: {exc}") from exc
