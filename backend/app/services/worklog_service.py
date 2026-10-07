"""S2-P4a-1 근무 기록 (시스템 입력이 원본 → 근무표 엑셀은 이 기록으로 생성, P4a-2)."""
from __future__ import annotations

import calendar
from datetime import date

from sqlalchemy import text

from app.database import get_dash_engine
from app.services import dash_db
from app.services.cost_calc import effective_on
from app.services.manager_service import _hm, _iso, today
from app.services.worker_service import _managers
from app.services.worklog_calc import check_log, day_result, month_summary

SQL_LOGS = "SELECT * FROM work_logs WHERE deleted_at IS NULL AND work_date BETWEEN :a AND :b"
SQL_WORKERS = "SELECT id, name, income_type, active FROM workers WHERE deleted_at IS NULL ORDER BY name"
SHEET_OF = {"employee": "labor", "business": "business", "freelancer": "business"}   # 근로소득 / 사업소득 파일


def month_bounds(m: date) -> tuple[date, date]:
    first = m.replace(day=1)
    return first, first.replace(day=calendar.monthrange(first.year, first.month)[1])


def _closed(conn, d: date) -> bool:
    return conn.execute(text("SELECT 1 FROM month_closings WHERE month = :m AND reopened_at IS NULL"),
                        {"m": d.replace(day=1)}).fetchone() is not None


def _group(rows: list[dict], key: str) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r[key], []).append(r)
    return out


def _hourly(r: dict | None) -> bool:
    return r is not None and r.get("pay_type") == "hourly"


def contract_out(r: dict | None) -> dict | None:
    if not _hourly(r):
        return None
    return {"amount": int(r["amount"]), "work_start": _hm(r.get("work_start")), "work_end": _hm(r.get("work_end")),
            "break_min": int(r.get("break_min") or 0), "break_paid": bool(r.get("break_paid")),
            "has_ot_rule": int(r.get("ot_unit_min") or 0) > 0 and int(r.get("ot_unit_amount") or 0) > 0,
            "vat_applied": bool(r.get("vat_applied"))}


def log_out(lg: dict, rate: dict | None) -> dict:
    d = day_result(lg, rate) if _hourly(rate) else None
    return {"id": lg["id"], "work_date": _iso(lg["work_date"]), "punch_in": _hm(lg.get("punch_in")),
            "clock_in": _hm(lg["clock_in"]), "clock_out": _hm(lg["clock_out"]),
            "break_min": lg.get("break_min"), "manager_id": lg.get("manager_id"),
            "memo": lg.get("memo"), "source": lg.get("source"),
            "paid_min": d["paid"] if d else None, "ot_min": d["ot"] if d else None,
            "ot_pay": d["ot_pay"] if d else None, "sheet_break": d["break"] if d else None,
            "no_contract": d is None}


def month_view(month: date) -> dict:
    first, last = month_bounds(month)
    rates = _group(dash_db.rows("SELECT * FROM worker_pay_rates WHERE deleted_at IS NULL"), "worker_id")
    logs = _group(dash_db.rows(SQL_LOGS + " ORDER BY work_date", {"a": first, "b": last}), "worker_id")
    with get_dash_engine().connect() as conn:
        closed = _closed(conn, first)
    people = []
    for w in dash_db.rows(SQL_WORKERS):
        rs, mine = rates.get(w["id"], []), logs.get(w["id"], [])
        cands = [effective_on(rs, first, "effective_from")] + [r for r in rs if first < r["effective_from"] <= last]
        hourly_in_month = any(_hourly(c) for c in cands)
        if not mine and not (w["active"] and hourly_in_month):
            continue
        s = month_summary(mine, rs)
        people.append({
            "worker_id": w["id"], "name": w["name"], "income_type": w["income_type"], "active": bool(w["active"]),
            "sheet": SHEET_OF.get(w["income_type"]),
            "contract": contract_out(effective_on(rs, last, "effective_from")),
            "days": {lg["work_date"].day: log_out(lg, effective_on(rs, lg["work_date"], "effective_from"))
                     for lg in mine},
            "summary": {k: s[k] for k in ("days", "nocontract", "paid_min", "ot_min", "base", "ot_allow")},
            "pay": s["pay"],
        })
    return {"month": first.isoformat(), "last_day": last.day, "closed": closed, "people": people}


def day_view(d: date) -> dict:
    rates = _group(dash_db.rows("SELECT * FROM worker_pay_rates WHERE deleted_at IS NULL"), "worker_id")
    accs = _group(dash_db.rows("SELECT * FROM worker_accounts WHERE deleted_at IS NULL"), "worker_id")
    logs = {lg["worker_id"]: lg for lg in dash_db.rows(SQL_LOGS, {"a": d, "b": d})}
    mgrs = _managers()
    items = []
    for w in dash_db.rows(SQL_WORKERS):
        r = effective_on(rates.get(w["id"], []), d, "effective_from")
        lg = logs.get(w["id"])
        if not lg and not (w["active"] and _hourly(r)):
            continue
        a = effective_on(accs.get(w["id"], []), d, "start_date")
        fixed = a["manager_id"] if a else None
        items.append({
            "worker_id": w["id"], "name": w["name"], "income_type": w["income_type"], "active": bool(w["active"]),
            "contract": contract_out(r),
            "fixed_manager_id": fixed, "fixed_manager_name": (mgrs.get(fixed) or {}).get("name"),
            "log": log_out(lg, r) if lg else None,
        })
    with get_dash_engine().connect() as conn:
        closed = _closed(conn, d)
    return {"date": d.isoformat(), "closed": closed, "future": d > today(), "items": items}


def save_day(d: date, items: list[dict], email: str) -> dict:
    """하루치 저장 (한 트랜잭션, 한 명이라도 오류면 전체 취소). 값이 같은 행은 다시 쓰지 않음."""
    t = today()
    warns: dict[str, list[str]] = {}
    saved = unchanged = 0
    with get_dash_engine().begin() as conn:
        if _closed(conn, d):
            raise ValueError(f"{d.year}년 {d.month}월은 마감되었습니다. 마감 해제 후 수정하세요")
        seen: set[int] = set()
        for it in items:
            wid = int(it["worker_id"])
            if wid in seen:
                raise ValueError("같은 인력이 두 번 들어 있습니다")
            seen.add(wid)
            w = conn.execute(text("SELECT name, active FROM workers WHERE id = :w AND deleted_at IS NULL"),
                             {"w": wid}).fetchone()
            if not w:
                raise ValueError("인력을 찾을 수 없습니다 (새로고침하세요)")
            rs = [dict(r) for r in conn.execute(text(
                "SELECT * FROM worker_pay_rates WHERE worker_id = :w AND deleted_at IS NULL"), {"w": wid}).mappings()]
            try:
                v = check_log(it.get("punch_in"), it.get("clock_out"), it.get("break_min"),
                              effective_on(rs, d, "effective_from"), day=d, today=t)
            except ValueError as e:
                raise ValueError(f"{w[0]}: {e}") from None
            if not w[1]:
                v["warns"].append("비활성 인력")
            mid, memo = it.get("manager_id"), it.get("memo")
            old = conn.execute(text("""
                SELECT id, punch_in, clock_in, clock_out, break_min, manager_id, memo FROM work_logs
                WHERE worker_id = :w AND work_date = :d AND deleted_at IS NULL
            """), {"w": wid, "d": d}).mappings().fetchone()
            if old and (old["punch_in"], old["clock_in"], old["clock_out"], old["break_min"], old["manager_id"],
                        old["memo"]) == (v["punch_in"], v["clock_in"], v["clock_out"], v["break_min"], mid, memo):
                unchanged += 1
                continue
            if old:
                conn.execute(text("UPDATE work_logs SET deleted_at = NOW(), deleted_by = :e WHERE id = :i"),
                             {"i": old["id"], "e": email})
            conn.execute(text("""
                INSERT INTO work_logs
                    (worker_id, work_date, punch_in, clock_in, clock_out, break_min, manager_id, source, memo, created_by)
                VALUES (:w, :d, :p, :i, :o, :b, :m, 'manual', :memo, :e)
            """), {"w": wid, "d": d, "p": v["punch_in"], "i": v["clock_in"], "o": v["clock_out"],
                   "b": v["break_min"], "m": mid, "memo": memo, "e": email})
            saved += 1
            if v["warns"]:
                warns[w[0]] = v["warns"]
    return {"ok": True, "saved": saved, "unchanged": unchanged, "warns": warns}


def delete_log(lid: int, email: str) -> None:
    """그날 기록 삭제 = 비근무. 변경 기록은 남김."""
    with get_dash_engine().begin() as conn:
        row = conn.execute(text("SELECT work_date FROM work_logs WHERE id = :i AND deleted_at IS NULL"),
                           {"i": lid}).fetchone()
        if not row:
            raise ValueError("기록을 찾을 수 없습니다 (이미 수정·삭제됨 — 새로고침하세요)")
        if _closed(conn, row[0]):
            raise ValueError("마감된 달의 기록은 삭제할 수 없습니다")
        conn.execute(text("UPDATE work_logs SET deleted_at = NOW(), deleted_by = :e WHERE id = :i"),
                     {"i": lid, "e": email})
