from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field

IncomeType = Literal["regular", "employee", "business", "freelancer"]


class WorkerIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    income_type: IncomeType = "employee"
    active: bool = True
    memo: str | None = Field(default=None, max_length=500)


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