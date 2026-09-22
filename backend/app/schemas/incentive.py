from pydantic import BaseModel


class IncentiveOne(BaseModel):
    date: str
    manager_id: int
    stops: int
    meals: int
    accounts: int
    product_incentive: int
    account_incentive: int
    total_incentive: int


class IncentiveRow(BaseModel):
    manager_id: int
    stops: int
    meals: int
    accounts: int
    product_incentive: int
    account_incentive: int
    total_incentive: int


class IncentiveAll(BaseModel):
    date: str
    managers: list[IncentiveRow]
    total_incentive_sum: int
