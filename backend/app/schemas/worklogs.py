from datetime import date, time

from pydantic import BaseModel, Field, model_validator


class WorkLogItem(BaseModel):
    worker_id: int
    punch_in: time | None = None          # 지문 출근 (비우면 지정 출근)
    clock_out: time                       # 지문 퇴근
    break_min: int | None = Field(default=None, ge=0, le=600)   # 비우면 계약 휴게
    manager_id: int | None = None         # 그날만 다른 계정을 쓴 경우 (NULL = 고정 계정)
    memo: str | None = Field(default=None, max_length=200)


class WorkDayIn(BaseModel):
    items: list[WorkLogItem] = Field(min_length=1, max_length=200)


class WorkLogDay(BaseModel):
    """사람별 입력 (월 표 팝업): 한 사람의 여러 날."""
    work_date: date
    punch_in: time | None = None
    clock_out: time
    break_min: int | None = Field(default=None, ge=0, le=600)
    manager_id: int | None = None
    memo: str | None = Field(default=None, max_length=200)


class WorkPersonIn(BaseModel):
    items: list[WorkLogDay] = Field(default_factory=list, max_length=31)
    delete_ids: list[int] = Field(default_factory=list, max_length=31)

    @model_validator(mode="after")
    def _not_empty(self):
        if not self.items and not self.delete_ids:
            raise ValueError("저장하거나 삭제할 기록이 없습니다")
        return self
