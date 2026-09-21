from pydantic import BaseModel


class StatusProgress(BaseModel):
    completed: int
    total: int
    unassigned: int


class DeliveryStatusResponse(BaseModel):
    date: str
    state: str          # PREVIEW | LIVE | RESULT | NONE
    incomplete: int     # RESULT 상태에서 미완료(미배송·기록누락) 건수
    cutoff_at: str
    now: str
    progress: StatusProgress
