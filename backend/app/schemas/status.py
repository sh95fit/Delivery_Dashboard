from pydantic import BaseModel


class StatusProgress(BaseModel):
    completed: int
    total: int
    unassigned: int


class StatusEstimate(BaseModel):
    total: int                    # 예상 Stops (배송지 수)
    estimated_meals: int
    estimated_accounts: int
    estimated_net_revenue: int


class DeliveryStatusResponse(BaseModel):
    date: str
    state: str          # PREVIEW | LIVE | RESULT | NONE
    incomplete: int     # RESULT 상태에서 미완료 건수
    cutoff_at: str
    now: str
    progress: StatusProgress
    estimate: StatusEstimate | None = None   # delivery 없는 PREVIEW에서만 존재
