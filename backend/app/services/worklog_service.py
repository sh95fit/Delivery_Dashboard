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


def _spans(rs: list[dict], key: str, first: date, last: date) -> list[dict]:
    """그 달에 적용되는 이력: 1일 기준 적용분 + 달 중간 시작분 (시작일 순)."""
    rs = sorted(rs, key=lambda r: r[key])
    head = effective_on(rs, first, key)
    return ([head] if head else []) + [r for r in rs if first < r[key] <= last]


def month_view(month: date) -> dict:
    first, last = month_bounds(month)
    rates = _group(dash_db.rows("SELECT * FROM worker_pay_rates WHERE deleted_at IS NULL"), "worker_id")
    accs = _group(dash_db.rows("SELECT * FROM worker_accounts WHERE deleted_at IS NULL"), "worker_id")
    logs = _group(dash_db.rows(SQL_LOGS + " ORDER BY work_date", {"a": first, "b": last}), "worker_id")
    mgrs = _managers()
    with get_dash_engine().connect() as conn:
        closed = _closed(conn, first)
    people = []
    for w in dash_db.rows(SQL_WORKERS):
        rs, mine = rates.get(w["id"], []), logs.get(w["id"], [])
        cands = _spans(rs, "effective_from", first, last)
        if not mine and not (w["active"] and any(_hourly(c) for c in cands)):
            continue
        s = month_summary(mine, rs)
        people.append({
            "worker_id": w["id"], "name": w["name"], "income_type": w["income_type"], "active": bool(w["active"]),
            "sheet": SHEET_OF.get(w["income_type"]),
            "contract": contract_out(effective_on(rs, last, "effective_from")),
            # 월 표 팝업: 날짜마다 그날 계약·고정 계정을 고르기 위한 이력
            "contracts": [{"from": _iso(r["effective_from"]), "contract": contract_out(r)} for r in cands],
            "accounts": [{"from": _iso(a["start_date"]), "manager_id": a["manager_id"],
                          "manager_name": (mgrs.get(a["manager_id"]) or {}).get("name")}
                         for a in _spans(accs.get(w["id"], []), "start_date", first, last)],
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


def _worker(conn, wid: int):
    w = conn.execute(text("SELECT name, active FROM workers WHERE id = :w AND deleted_at IS NULL"),
                     {"w": wid}).fetchone()
    if not w:
        raise ValueError("인력을 찾을 수 없습니다 (새로고침하세요)")
    return w


def _rates(conn, wid: int) -> list[dict]:
    return [dict(r) for r in conn.execute(text(
        "SELECT * FROM worker_pay_rates WHERE worker_id = :w AND deleted_at IS NULL"), {"w": wid}).mappings()]


def _write(conn, wid: int, d: date, it: dict, rs: list[dict], email: str, t: date) -> tuple[bool, list[str]]:
    """한 사람·하루 저장 → (새로 썼는지, 경고). 값이 같으면 다시 쓰지 않음. 수정 = 기존 행 삭제 표시 + 새 행."""
    v = check_log(it.get("punch_in"), it.get("clock_out"), it.get("break_min"),
                  effective_on(rs, d, "effective_from"), day=d, today=t)
    mid, memo = it.get("manager_id"), it.get("memo")
    old = conn.execute(text("""
        SELECT id, punch_in, clock_in, clock_out, break_min, manager_id, memo FROM work_logs
        WHERE worker_id = :w AND work_date = :d AND deleted_at IS NULL
    """), {"w": wid, "d": d}).mappings().fetchone()
    if old and (old["punch_in"], old["clock_in"], old["clock_out"], old["break_min"], old["manager_id"],
                old["memo"]) == (v["punch_in"], v["clock_in"], v["clock_out"], v["break_min"], mid, memo):
        return False, v["warns"]
    if old:
        conn.execute(text("UPDATE work_logs SET deleted_at = NOW(), deleted_by = :e WHERE id = :i"),
                     {"i": old["id"], "e": email})
    conn.execute(text("""
        INSERT INTO work_logs
            (worker_id, work_date, punch_in, clock_in, clock_out, break_min, manager_id, source, memo, created_by)
        VALUES (:w, :d, :p, :i, :o, :b, :m, 'manual', :memo, :e)
    """), {"w": wid, "d": d, "p": v["punch_in"], "i": v["clock_in"], "o": v["clock_out"],
           "b": v["break_min"], "m": mid, "memo": memo, "e": email})
    return True, v["warns"]


def save_day(d: date, items: list[dict], email: str) -> dict:
    """일일 입력: 하루 × 여러 사람 (한 트랜잭션, 한 명이라도 오류면 전체 취소)."""
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
            w = _worker(conn, wid)
            try:
                wrote, ws = _write(conn, wid, d, it, _rates(conn, wid), email, t)
            except ValueError as e:
                raise ValueError(f"{w[0]}: {e}") from None
            if not wrote:
                unchanged += 1
                continue
            saved += 1
            ws = ws + ([] if w[1] else ["비활성 인력"])
            if ws:
                warns[w[0]] = ws
    return {"ok": True, "saved": saved, "unchanged": unchanged, "warns": warns}


def save_person(wid: int, items: list[dict], delete_ids: list[int], email: str) -> dict:
    """월 표 팝업: 한 사람 × 여러 날 저장·삭제 (한 트랜잭션, 하루라도 오류면 전체 취소)."""
    t = today()
    warns: dict[str, list[str]] = {}
    saved = unchanged = deleted = 0
    days = [it["work_date"] for it in items]
    if len(set(days)) != len(days):
        raise ValueError("같은 날짜가 두 번 들어 있습니다")
    with get_dash_engine().begin() as conn:
        w = _worker(conn, wid)
        targets: list[tuple[int, date]] = []
        for lid in dict.fromkeys(delete_ids):
            row = conn.execute(text("""SELECT work_date FROM work_logs
                                       WHERE id = :i AND worker_id = :w AND deleted_at IS NULL"""),
                               {"i": lid, "w": wid}).fetchone()
            if not row:
                raise ValueError("삭제할 기록을 찾을 수 없습니다 (이미 수정·삭제됨 — 새로고침하세요)")
            if row[0] in days:
                raise ValueError(f"{row[0]}: 같은 날을 저장과 삭제에 함께 넣을 수 없습니다")
            targets.append((lid, row[0]))
        for m in sorted({d.replace(day=1) for d in days} | {d.replace(day=1) for _, d in targets}):
            if _closed(conn, m):
                raise ValueError(f"{m.year}년 {m.month}월은 마감되었습니다. 마감 해제 후 수정하세요")
        for lid, _ in targets:
            conn.execute(text("UPDATE work_logs SET deleted_at = NOW(), deleted_by = :e WHERE id = :i"),
                         {"i": lid, "e": email})
            deleted += 1
        rs = _rates(conn, wid)
        for it in sorted(items, key=lambda x: x["work_date"]):
            d = it["work_date"]
            try:
                wrote, ws = _write(conn, wid, d, it, rs, email, t)
            except ValueError as e:
                raise ValueError(f"{d.month}/{d.day}: {e}") from None
            if not wrote:
                unchanged += 1
                continue
            saved += 1
            ws = ws + ([] if w[1] else ["비활성 인력"])
            if ws:
                warns[f"{d.month}/{d.day}"] = ws
    return {"ok": True, "saved": saved, "unchanged": unchanged, "deleted": deleted, "warns": warns}


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
