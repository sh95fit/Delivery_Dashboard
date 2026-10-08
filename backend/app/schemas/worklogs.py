from datetime import time

from pydantic import BaseModel, Field


class WorkLogItem(BaseModel):
    worker_id: int
    punch_in: time | None = None          # 지문 출근 (비우면 지정 출근)
    clock_out: time                       # 지문 퇴근
    break_min: int | None = Field(default=None, ge=0, le=600)   # 비우면 계약 휴게
    manager_id: int | None = None         # 그날만 다른 계정을 쓴 경우 (NULL = 고정 계정)
    memo: str | None = Field(default=None, max_length=200)


class WorkDayIn(BaseModel):
    items: list[WorkLogItem] = Field(min_length=1, max_length=200)
