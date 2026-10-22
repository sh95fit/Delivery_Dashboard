from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_email, is_admin_email
from app.services import route_leg_service, routes_service

router = APIRouter(prefix="/routes", tags=["routes"])


# [S3-P2d-2b-1] 지도: 실제 경로(route_legs) · 남은 경로 미리보기 (기존 경로 API보다 먼저 선언)
@router.get("/{target_date}/legs")
def get_route_legs(target_date: date_type, dwell_min: int | None = Query(default=None, ge=1, le=30),
                   _: str = Depends(get_current_email)):
    try:
        return route_leg_service.legs_view(target_date, dwell_min)   # [S3-P2d-5c] dwell_min = 정차 임의 설정(분)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"실제 경로 조회 실패: {exc}") from exc


@router.get("/{target_date}/preview-all")
def get_preview_all(target_date: date_type, _: str = Depends(get_current_email)):
    return route_leg_service.preview_all_status(target_date)


@router.post("/{target_date}/preview-all")
def post_preview_all(target_date: date_type, _: str = Depends(get_current_email)):
    try:
        return route_leg_service.start_preview_all(target_date)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"전체 미리보기 시작 실패: {exc}") from exc


@router.post("/{target_date}/{manager_id}/preview")
def post_route_preview(target_date: date_type, manager_id: int, _: str = Depends(get_current_email)):
    try:
        return route_leg_service.preview(target_date, manager_id)
    except route_leg_service.StopCalls as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"남은 경로 계산 실패: {exc}") from exc


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
