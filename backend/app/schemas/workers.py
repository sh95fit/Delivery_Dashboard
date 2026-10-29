from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field

IncomeType = Literal["regular", "employee", "business", "freelancer"]


class WorkerIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    income_type: IncomeType = "employee"
    active: bool = True
    memo: str | None = Field(default=None, max_length=500)
    end_date: date | None = None              # [S2-P0c] 퇴사일 (비활성일 때 필수)
    last_pay_full: bool = True                # 정규직 마지막 달 월급 그대로 지급
    last_pay_amount: int | None = Field(default=None, ge=0, le=100_000_000)


class WorkerRateIn(BaseModel):
    effective_from: date
    pay_type: Literal["monthly", "hourly", "none"]
    amount: int = Field(default=0, ge=0, le=100_000_000)
    vat_applied: bool = False
    work_start: time | None = None
    work_end: time | None = None
    break_min: int = Field(default=0, ge=0, le=600)
    break_paid: bool = True
    ot_unit_min: int = Field(default=0, ge=0, le=600)
    ot_unit_amount: int = Field(default=0, ge=0, le=1_000_000)
    work_days: int = Field(default=31, ge=0, le=127)   # 근무 요일 비트, 기본 월~금 (0은 check_rate가 안내 문구로 거절)    
    memo: str | None = Field(default=None, max_length=200)


class WorkerAccountIn(BaseModel):
    manager_id: int | None = None
    start_date: date


class ImportExcelIn(BaseModel):
    file_name: str = Field(default="", max_length=255)
    content_b64: str = Field(min_length=1, max_length=3_000_000)
    file_income: Literal["employee", "business"] = "employee"


class ImportRow(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    income_type: IncomeType
    memo: str | None = Field(default=None, max_length=500)
    rate: WorkerRateIn | None = None
    manager_id: int | None = None
    account_from: date | None = None


class ImportCommitIn(BaseModel):
    rows: list[ImportRow] = Field(min_length=1, max_length=300)
    
    
class WorkerVehicleIn(BaseModel):          # [S3-P2h-2a] 차량 이용 이력 (시작일부터 다음 이력 전날까지)
    start_date: date
    mode: Literal["company", "own", "none"]
    vehicle_id: int | None = None
    memo: str | None = Field(default=None, max_length=200)


class WorkerVehicleDayIn(BaseModel):       # [S3-P2h-2a] 그날 예외 (vehicle_id 비움 = 그날 회사 차량 없음)
    work_date: date
    vehicle_id: int | None = None
    reason: Literal["breakdown", "swap", "other"] = "other"
    memo: str | None = Field(default=None, max_length=200)
    