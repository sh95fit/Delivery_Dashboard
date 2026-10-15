"""S3-P1b-1 영업일 달력 = 규칙(business_days) + 날짜별 예외(business_day_overrides).
유류비·기간 비용을 영업일로 나눌 때 open_days()를 사용."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text

from app.database import get_dash_engine
from app.services import dash_db
from app.services.business_days import business_days, day_status
from app.services.cost_calc import days_incl

MAX_DAYS = 400


def overrides(frm: date, to: date) -> dict[date, dict]:
    rows = dash_db.rows("""SELECT id, work_date, is_open, memo, created_by FROM business_day_overrides
        WHERE deleted_at IS NULL AND work_date BETWEEN :a AND :b""", {"a": frm, "b": to})
    return {r["work_date"]: r for r in rows}


def open_days(frm: date, to: date) -> list[date]:
    return business_days(frm, to, overrides(frm, to))


def day_list(frm: date, to: date) -> dict:
    if to < frm:
        raise ValueError("조회 종료일이 시작일보다 빠릅니다")
    if days_incl(frm, to) > MAX_DAYS:
        raise ValueError(f"조회 기간은 {MAX_DAYS}일 이내로 지정하세요")
    ov = overrides(frm, to)
    items = []
    d = frm
    while d <= to:
        is_open, why, basis = day_status(d, ov)
        o = ov.get(d)
        items.append({"date": d.isoformat(), "weekday": d.weekday(), "open": is_open, "why": why,
                      "basis": basis, "created_by": o["created_by"] if o else None})
        d += timedelta(days=1)
    return {"from": frm.isoformat(), "to": to.isoformat(),
            "open_days": sum(1 for i in items if i["open"]), "items": items}


def set_override(d: date, is_open: bool, memo: str | None, email: str) -> int:
    """그날 영업/휴무를 규칙과 다르게 지정. 기존 지정은 삭제 기록을 남기고 새로 저장."""
    with get_dash_engine().begin() as conn:
        conn.execute(text("""UPDATE business_day_overrides SET deleted_at = NOW(), deleted_by = :e
            WHERE work_date = :d AND deleted_at IS NULL"""), {"d": d, "e": email})
        return int(conn.execute(text("""INSERT INTO business_day_overrides (work_date, is_open, memo, created_by)
            VALUES (:d, :o, :m, :e) RETURNING id"""), {"d": d, "o": bool(is_open), "m": memo, "e": email}).scalar_one())


def clear_override(d: date, email: str) -> None:
    with get_dash_engine().begin() as conn:
        res = conn.execute(text("""UPDATE business_day_overrides SET deleted_at = NOW(), deleted_by = :e
            WHERE work_date = :d AND deleted_at IS NULL"""), {"d": d, "e": email})
    if res.rowcount == 0:
        raise ValueError("이 날짜에 지정된 예외가 없습니다")
