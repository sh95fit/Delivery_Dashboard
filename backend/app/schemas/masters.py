from datetime import date, time
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
    work_start: time | None = None
    work_end: time | None = None
    break_min: int = Field(default=0, ge=0, le=600)
    break_paid: bool = False    


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
    vat_deductible: bool = False    


class PeriodCostIn(BaseModel):
    vehicle_id: int
    category: Literal["insurance", "tax", "inspection", "lease", "other"]
    amount: int = Field(gt=0, le=1_000_000_000)
    start_date: date
    end_date: date
    memo: str | None = Field(default=None, max_length=200)


class ExpenseIn(BaseModel):
    vehicle_id: int
    expense_date: date
    category: Literal["repair", "maintenance", "tire", "towing", "accident", "depreciation", "parking", "wash", "other"]
    amount: int = Field(gt=0, le=1_000_000_000)
    memo: str | None = Field(default=None, max_length=200)


class FuelPriceIn(BaseModel):
    price_date: date
    fuel_type: Literal["gasoline", "diesel", "lpg", "ev"]
    price: float = Field(gt=0, le=10000)
    memo: str | None = Field(default=None, max_length=200)


class DayOverrideIn(BaseModel):
    is_open: bool
    memo: str | None = Field(default=None, max_length=200)


class FuelLogIn(BaseModel):
    vehicle_id: int
    fuel_date: date
    fuel_type: Literal["gasoline", "diesel", "lpg", "ev"] | None = None
    quantity: float | None = Field(default=None, gt=0, le=100000)
    unit_price: float | None = Field(default=None, gt=0, le=10000)
    total_amount: int = Field(gt=0, le=100_000_000)
    supply_amount: int | None = Field(default=None, ge=0, le=100_000_000)
    vat_amount: int | None = Field(default=None, ge=0, le=100_000_000)
    station: str | None = Field(default=None, max_length=100)
    memo: str | None = Field(default=None, max_length=200)


class FuelCloseIn(BaseModel):
    memo: str | None = Field(default=None, max_length=200)


class FuelReleaseIn(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


class FuelImportPreviewIn(BaseModel):
    file_name: str | None = Field(default=None, max_length=200)
    content_b64: str = Field(min_length=1, max_length=3_000_000)
    vehicle_map: dict[str, int] = Field(default_factory=dict)


class FuelImportIn(FuelImportPreviewIn):
    rows: list[int] = Field(min_length=1, max_length=2000)


class FuelUndoIn(BaseModel):
    reason: str = Field(min_length=1, max_length=200)


class EvRateFileIn(BaseModel):
    file_name: str | None = Field(default=None, max_length=200)
    content_b64: str = Field(min_length=1, max_length=3_000_000)


class EvRateCommitIn(EvRateFileIn):
    speed: Literal["slow", "fast", "ultra"]
    effective_from: date
    memo: str | None = Field(default=None, max_length=200)


class EvSettingsIn(BaseModel):
    ev_speed: Literal["slow", "fast", "ultra"]
    ev_km_per_kwh: float = Field(gt=0, le=20)
