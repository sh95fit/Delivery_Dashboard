from pydantic import BaseModel


class StatusProgress(BaseModel):
    completed: int
    total: int
    unassigned: int


class StatusEstimate(BaseModel):
    total: int
    estimated_meals: int
    estimated_accounts: int
    estimated_net_revenue: int          # VAT 제외, 총매출 - 환불
    estimated_gross_revenue: int = 0    # VAT 제외
    estimated_refund_amount: int = 0    # VAT 제외
    lunch_meals: int = 0
    dinner_meals: int = 0
    web_qty: int = 0
    admin_qty: int = 0
    app_qty: int = 0
    app_converted_qty: int = 0
    app_pending_qty: int = 0


class DeliveryStatusResponse(BaseModel):
    date: str
    state: str
    incomplete: int
    cutoff_at: str
    now: str
    progress: StatusProgress
    estimate: StatusEstimate | None = None
    source: str | None = None
    mode: str | None = None
    cutoff_source: str | None = None
    estimated: bool = False
    totals: dict | None = None
    warnings: dict | None = None
    internal: dict | None = None
    production: dict | None = None