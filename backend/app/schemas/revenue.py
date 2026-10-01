from pydantic import BaseModel


class LineupAmount(BaseModel):
    name: str
    qty: int
    amount: int                      # 순매출(VAT 제외) — 기존 의미 유지
    meal: str | None = None
    refund_qty: int = 0
    gross_revenue: int = 0
    refund_amount: int = 0
    net_revenue: int = 0
    internal_qty: int = 0
    internal_net: int = 0


class ManagerLineup(BaseModel):
    name: str
    qty: int
    amount: int


class RevenueTotal(BaseModel):
    net_revenue: int
    meals: int
    stops: int
    accounts: int
    lunch_meals: int = 0
    dinner_meals: int = 0
    web_qty: int = 0
    admin_qty: int = 0
    app_qty: int = 0
    refund_qty: int = 0
    gross_revenue: int = 0
    refund_amount: int = 0
    estimated_revenue: int = 0
    internal_meals: int = 0
    internal_net: int = 0


class ManagerRevenue(BaseModel):
    manager_id: int | None
    manager_name: str | None
    stops: int
    meals: int
    accounts: int
    net_revenue: int
    lunch_meals: int = 0
    dinner_meals: int = 0
    gross_revenue: int = 0
    refund_amount: int = 0
    internal_meals: int = 0
    internal_net: int = 0
    lineups: dict[str, ManagerLineup]


class DayRevenue(BaseModel):
    date: str
    estimated: bool
    stops: int
    meals: int
    gross_revenue: int
    refund_amount: int
    net_revenue: int
    internal_net: int = 0


class RevenueSummaryResponse(BaseModel):
    from_date: str
    to_date: str
    days: int = 0
    estimated_days: int = 0
    total: RevenueTotal
    by_manager: list[ManagerRevenue]
    by_lineup: dict[str, LineupAmount]
    by_day: list[DayRevenue] = []
