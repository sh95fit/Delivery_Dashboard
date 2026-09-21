from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_email
from app.schemas.revenue import RevenueSummaryResponse
from app.services import revenue_service

router = APIRouter(prefix="/revenue", tags=["revenue"])


@router.get("/summary", response_model=RevenueSummaryResponse)
def revenue_summary(
    from_date: date_type = Query(alias="from"),
    to_date: date_type = Query(alias="to"),
    _: str = Depends(get_current_email),
):
    if from_date > to_date:
        raise HTTPException(status_code=400, detail="from은 to보다 이전이어야 합니다")
    try:
        return revenue_service.get_revenue_summary(from_date, to_date)
    except TimeoutError:
        raise HTTPException(status_code=504, detail="조회 시간 초과 — 잠시 후 다시 시도하세요")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"순매출 집계 실패: {exc}") from exc
