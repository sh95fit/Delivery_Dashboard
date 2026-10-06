"""dash_db 소형 헬퍼 (S1-P1)."""
from __future__ import annotations

from sqlalchemy import text

from app.database import get_dash_engine

SOFT_TABLES = {"manager_pay_rates", "vehicle_assignments", "vehicles", "vehicle_period_costs", "vehicle_expenses",
               "worker_pay_rates", "worker_accounts"}


def rows(sql: str, params: dict | None = None) -> list[dict]:
    with get_dash_engine().connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), params or {}).mappings().all()]


def insert_id(sql: str, params: dict) -> int:
    with get_dash_engine().begin() as conn:
        return int(conn.execute(text(sql), params).scalar_one())


def soft_delete(table: str, item_id: int, email: str) -> None:
    if table not in SOFT_TABLES:
        raise ValueError("삭제할 수 없는 대상입니다")
    with get_dash_engine().begin() as conn:
        res = conn.execute(
            text(f"UPDATE {table} SET deleted_at = NOW(), deleted_by = :e WHERE id = :i AND deleted_at IS NULL"),
            {"i": int(item_id), "e": email},
        )
    if res.rowcount == 0:
        raise ValueError("대상을 찾을 수 없거나 이미 삭제되었습니다")
