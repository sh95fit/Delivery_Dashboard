from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class ProfileIn(BaseModel):
    active: bool = True
    memo: str | None = Field(default=None, max_length=500)


class PayRateIn(BaseModel):
    pay_type: Literal["monthly", "hourly", "none"]
    amount: int = Field(default=0, ge=0, le=100_000_000)
    effective_from: date
    memo: str | None = Field(default=None, max_length=200)


class AssignIn(BaseModel):
    vehicle_id: int | None = None
    start_date: date


class VehicleIn(BaseModel):
    plate_no: str = Field(min_length=1, max_length=20)
    model: str | None = Field(default=None, max_length=100)
    fuel_type: Literal["gasoline", "diesel", "lpg", "ev"] = "diesel"
    fuel_efficiency: float | None = Field(default=None, gt=0, le=100)
    purchase_date: date | None = None
    purchase_price: int | None = Field(default=None, ge=0)
    memo: str | None = Field(default=None, max_length=500)
    active: bool = True


class PeriodCostIn(BaseModel):
    vehicle_id: int
    category: Literal["insurance", "tax", "inspection", "other"]
    amount: int = Field(gt=0, le=1_000_000_000)
    start_date: date
    end_date: date
    memo: str | None = Field(default=None, max_length=200)


class ExpenseIn(BaseModel):
    vehicle_id: int
    expense_date: date
    category: Literal["repair", "maintenance", "tire", "depreciation", "parking", "wash", "other"]
    amount: int = Field(gt=0, le=1_000_000_000)
    memo: str | None = Field(default=None, max_length=200)
