from pydantic import BaseModel


class LineupQty(BaseModel):
    name: str
    qty: int
    amount: int | None = None


class ManagerDelivery(BaseModel):
    manager_id: int | None
    manager_name: str | None
    color: str | None
    stops: int
    meals: int
    accounts: int
    net_revenue: int
    lineups: dict[str, LineupQty]


class StopPoint(BaseModel):
    delivery_id: str
    address_id: int
    address_name: str | None
    latitude: float
    longitude: float
    delivery_hour_raw: str | None = None
    delivery_time: str | None = None
    manager_id: int | None
    manager_name: str | None
    manager_color: str | None
    accounts: int
    meals: int
    lineups: dict[str, LineupQty]


class DeliveryDayResponse(BaseModel):
    date: str
    summary: dict
    managers: list[ManagerDelivery]
    unassigned: dict
    stops: list[StopPoint]
