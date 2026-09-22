from pydantic import BaseModel, field_validator


class AdjustRequest(BaseModel):
    field: str
    value: int
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_required(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("사유는 필수입니다")
        return v.strip()


class HoldRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_required(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("사유는 필수입니다")
        return v.strip()


class AdjustmentLog(BaseModel):
    field: str
    value: int
    reason: str
    created_by: str | None = None
    created_at: str | None = None


class IncentiveRow(BaseModel):
    manager_id: int
    stops: int
    gajung_qty: int
    mil_qty: int
    collection_count: int
    accounts: int
    product_total: int
    product_incentive: int
    account_incentive: int
    total_incentive: int
    is_held: bool
    hold_reason: str | None = None
    payable_incentive: int
    adjustments: list[AdjustmentLog] = []
    auto: dict


class IncentiveOne(BaseModel):
    date: str
    manager_id: int
    stops: int
    gajung_qty: int
    mil_qty: int
    collection_count: int
    accounts: int
    product_total: int
    product_incentive: int
    account_incentive: int
    total_incentive: int
    is_held: bool
    hold_reason: str | None = None
    payable_incentive: int
    adjustments: list[AdjustmentLog] = []
    auto: dict


class IncentiveAll(BaseModel):
    date: str
    managers: list[IncentiveRow]
    total_incentive_sum: int
    payable_incentive_sum: int
