"""S2-P4c-1 인센티브 입력 스키마."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _need(v: str) -> str:
    v = (v or "").strip()
    if not v:
        raise ValueError("사유는 필수입니다")
    return v


class Band(BaseModel):
    start: int = Field(ge=0)
    end: int | None = Field(default=None, ge=1)
    amount: int = Field(ge=0, le=1_000_000)


class RateSetIn(BaseModel):
    effective_from: date
    product: list[Band] = Field(min_length=1, max_length=20)
    account: list[Band] = Field(min_length=1, max_length=20)
    memo: str | None = Field(default=None, max_length=200)


class AccountItem(BaseModel):
    manager_id: int
    value: int | None = Field(default=None, ge=0, le=500)    # None = 입력 지우기


class AccountsIn(BaseModel):
    items: list[AccountItem] = Field(min_length=1, max_length=200)


class QtyAdjIn(BaseModel):
    work_date: date
    manager_id: int
    product_id: int | None = None                              # None = 제품 총량
    qty: int = Field(ge=-2000, le=2000)                        # 0은 서버에서 거절
    reason: str = Field(max_length=200)
    _r = field_validator("reason")(classmethod(lambda cls, v: _need(v)))


class ExclusionIn(BaseModel):
    work_date: date
    manager_id: int
    address_id: int
    reason: Literal["quick", "other_manager", "not_delivered", "other"]
    memo: str | None = Field(default=None, max_length=200)


class ExtraItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    unit_amount: int | None = Field(default=None, gt=0, le=1_000_000)
    active: bool = True
    sort_order: int = 0
    memo: str | None = Field(default=None, max_length=200)


class ExtraIn(BaseModel):
    work_date: date
    manager_id: int
    item_id: int
    qty: int = Field(default=1, ge=1, le=50)
    unit_amount: int | None = Field(default=None, gt=0, le=1_000_000)   # 비우면 품목 기본 금액
    memo: str | None = Field(default=None, max_length=200)


class ExtraUpdateIn(BaseModel):
    qty: int = Field(ge=1, le=50)
    unit_amount: int | None = Field(default=None, gt=0, le=1_000_000)
    memo: str | None = Field(default=None, max_length=200)


class ReasonIn(BaseModel):
    reason: str = Field(max_length=200)
    _r = field_validator("reason")(classmethod(lambda cls, v: _need(v)))


class HoldIn(BaseModel):
    manager_id: int
    reason: str = Field(max_length=200)
    _r = field_validator("reason")(classmethod(lambda cls, v: _need(v)))

class OwnerIn(BaseModel):
    manager_id: int
    worker_id: int | None = None                               # None = 지정 해제 (기본 규칙으로)
    memo: str | None = Field(default=None, max_length=200)
