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
    gross_revenue: int = 0
    refund_amount: int = 0
    lunch_meals: int = 0
    dinner_meals: int = 0
    web_qty: int = 0
    admin_qty: int = 0
    app_qty: int = 0
    app_pending_qty: int = 0
    lineups: dict[str, LineupQty]


class StopPoint(BaseModel):
    delivery_id: str
    address_id: int | None
    address_name: str | None
    detail_address: str | None = None
    latitude: float | None
    longitude: float | None
    has_coord: bool = True
    delivery_hour_raw: str | None = None
    delivery_time: str | None = None
    manager_id: int | None
    manager_name: str | None
    manager_color: str | None
    accounts: int
    meals: int
    lunch_meals: int = 0
    dinner_meals: int = 0
    app_qty: int = 0
    app_pending_qty: int = 0
    net_revenue: int = 0
    lineups: dict[str, LineupQty]


class DeliveryDayResponse(BaseModel):
    date: str
    source: str
    mode: str | None = None
    estimated: bool = False
    cutoff_at: str | None = None
    summary: dict
    managers: list[ManagerDelivery]
    unassigned: dict
    stops: list[StopPoint]
    by_lineup: dict = {}
    warnings: dict = {}
