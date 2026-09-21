from pydantic import BaseModel


class StatusProgress(BaseModel):
    completed: int
    total: int
    unassigned: int


class DeliveryStatusResponse(BaseModel):
    date: str
    state: str          # PREVIEW | LIVE | RESULT | NONE
    cutoff_at: str
    now: str
    progress: StatusProgress
