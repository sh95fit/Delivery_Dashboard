from pydantic import BaseModel


class LineupAmount(BaseModel):
    name: str
    qty: int
    amount: int


class RevenueTotal(BaseModel):
    net_revenue: int
    meals: int
    stops: int
    accounts: int


class ManagerRevenue(BaseModel):
    manager_id: int | None
    manager_name: str | None
    stops: int
    meals: int
    accounts: int
    net_revenue: int
    lineups: dict[str, LineupAmount]


class RevenueSummaryResponse(BaseModel):
    from_date: str
    to_date: str
    total: RevenueTotal
    by_manager: list[ManagerRevenue]
    by_lineup: dict[str, LineupAmount]
