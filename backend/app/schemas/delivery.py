from pydantic import BaseModel


class LineupQty(BaseModel):
    name: str
    qty: int
    amount: int


class ManagerDelivery(BaseModel):
    manager_id: int | None
    manager_name: str | None
    color: str | None
    stops: int
    meals: int
    accounts: int
    net_revenue: int
    lineups: dict[str, LineupQty]


class DeliveryDayResponse(BaseModel):
    date: str
    summary: dict
    managers: list[ManagerDelivery]
    unassigned: dict
