"""S2-P4a-1 근무 기록 (시스템 입력이 원본 → 근무표 엑셀은 이 기록으로 생성, P4a-2)."""
from __future__ import annotations

import calendar
import io
import json
import os
import zipfile
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import get_dash_engine
from app.services import dash_db
from app.services.cost_calc import effective_on
from app.services.manager_service import _hm, _iso, today
from app.services.worker_service import _managers
from app.services.timesheet_export import SHEET_TITLE, build_timesheet, schedule_note, verify_timesheet
from app.services.worker_calc import pay_total
from app.services.worklog_calc import check_log, day_result, is_workday, month_summary, sheet_break


SQL_LOGS = "SELECT * FROM work_logs WHERE deleted_at IS NULL AND work_date BETWEEN :a AND :b"
SQL_WORKERS = "SELECT id, name, income_type, active FROM workers WHERE deleted_at IS NULL ORDER BY name"
SQL_OFFS = "SELECT * FROM work_offs WHERE deleted_at IS NULL AND work_date BETWEEN :a AND :b"
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
            "vat_applied": bool(r.get("vat_applied")),
            "work_days": 31 if r.get("work_days") is None else int(r["work_days"])}


def off_out(o: dict) -> dict:
    return {"id": o["id"], "work_date": _iso(o["work_date"]), "reason": o["reason"], "memo": o.get("memo")}


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
    offs = _group(dash_db.rows(SQL_OFFS, {"a": first, "b": last}), "worker_id")
    mgrs = _managers()
    end = min(last, today() - timedelta(days=1))          # 미입력 판정은 어제까지 (오늘은 입력 전일 수 있음)
    with get_dash_engine().connect() as conn:
        closed = _closed(conn, first)
    people = []
    for w in dash_db.rows(SQL_WORKERS):
        rs, mine, off = rates.get(w["id"], []), logs.get(w["id"], []), offs.get(w["id"], [])
        cands = _spans(rs, "effective_from", first, last)
        if not mine and not off and not (w["active"] and any(_hourly(c) for c in cands)):
            continue
        s = month_summary(mine, rs)
        done = {lg["work_date"] for lg in mine} | {o["work_date"] for o in off}
        missing = [] if not w["active"] else [
            d.day for d in (first + timedelta(days=i) for i in range((end - first).days + 1))
            if d not in done and is_workday(effective_on(rs, d, "effective_from"), d)]
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
            "offs": {o["work_date"].day: off_out(o) for o in off},
            "missing_days": missing,
            "summary": {k: s[k] for k in ("days", "nocontract", "paid_min", "ot_min", "base", "ot_allow",
                                          "weekend_days", "weekend_min")},
            "pay": s["pay"],
        })
    return {"month": first.isoformat(), "last_day": last.day, "closed": closed, "people": people}


def day_view(d: date) -> dict:
    rates = _group(dash_db.rows("SELECT * FROM worker_pay_rates WHERE deleted_at IS NULL"), "worker_id")
    accs = _group(dash_db.rows("SELECT * FROM worker_accounts WHERE deleted_at IS NULL"), "worker_id")
    logs = {lg["worker_id"]: lg for lg in dash_db.rows(SQL_LOGS, {"a": d, "b": d})}
    offs = {o["worker_id"]: o for o in dash_db.rows(SQL_OFFS, {"a": d, "b": d})}
    mgrs = _managers()
    items = []
    for w in dash_db.rows(SQL_WORKERS):
        r = effective_on(rates.get(w["id"], []), d, "effective_from")
        lg, off = logs.get(w["id"]), offs.get(w["id"])
        if not lg and not off and not (w["active"] and _hourly(r)):
            continue
        a = effective_on(accs.get(w["id"], []), d, "start_date")
        fixed = a["manager_id"] if a else None
        items.append({
            "worker_id": w["id"], "name": w["name"], "income_type": w["income_type"], "active": bool(w["active"]),
            "contract": contract_out(r), "workday": is_workday(r, d),
            "fixed_manager_id": fixed, "fixed_manager_name": (mgrs.get(fixed) or {}).get("name"),
            "log": log_out(lg, r) if lg else None,
            "off": off_out(off) if off else None,
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
    if conn.execute(text("SELECT 1 FROM work_offs WHERE worker_id = :w AND work_date = :d AND deleted_at IS NULL"),
                    {"w": wid, "d": d}).fetchone():
        raise ValueError("휴무로 지정된 날입니다 (월 표 한 달 입력에서 휴무를 해제한 뒤 입력하세요)")    
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


def _write_off(conn, wid: int, it: dict, email: str) -> bool:
    """휴무 지정·사유 수정 → 새로 썼는지. 같은 값이면 다시 쓰지 않음. 수정 = 기존 행 삭제 표시 + 새 행."""
    d = it["work_date"]
    if conn.execute(text("SELECT 1 FROM work_logs WHERE worker_id = :w AND work_date = :d AND deleted_at IS NULL"),
                    {"w": wid, "d": d}).fetchone():
        raise ValueError("근무 기록이 있는 날은 휴무로 지정할 수 없습니다 (퇴근을 지워 근무를 삭제한 뒤 지정)")
    old = conn.execute(text("""
        SELECT id, reason, memo FROM work_offs
        WHERE worker_id = :w AND work_date = :d AND deleted_at IS NULL
    """), {"w": wid, "d": d}).mappings().fetchone()
    if old and (old["reason"], old["memo"]) == (it["reason"], it.get("memo")):
        return False
    if old:
        conn.execute(text("UPDATE work_offs SET deleted_at = NOW(), deleted_by = :e WHERE id = :i"),
                     {"i": old["id"], "e": email})
    conn.execute(text("""
        INSERT INTO work_offs (worker_id, work_date, reason, memo, created_by)
        VALUES (:w, :d, :r, :m, :e)
    """), {"w": wid, "d": d, "r": it["reason"], "m": it.get("memo"), "e": email})
    return True


def save_person(wid: int, items: list[dict], delete_ids: list[int], email: str,
                offs: list[dict] | None = None, off_delete_ids: list[int] | None = None) -> dict:
    """월 표 팝업: 한 사람 × 여러 날 근무·휴무 저장/삭제 (한 트랜잭션, 하루라도 오류면 전체 취소).
    순서: 근무 삭제 → 휴무 해제 → 휴무 지정 → 근무 저장 (같은 날 근무↔휴무 전환을 한 번에 처리)"""
    offs, off_delete_ids = offs or [], off_delete_ids or []
    t = today()
    warns: dict[str, list[str]] = {}
    saved = unchanged = deleted = off_saved = off_deleted = 0
    days = [it["work_date"] for it in items]
    off_days = [o["work_date"] for o in offs]
    if len(set(days)) != len(days) or len(set(off_days)) != len(off_days):
        raise ValueError("같은 날짜가 두 번 들어 있습니다")
    both = set(days) & set(off_days)
    if both:
        d = min(both)
        raise ValueError(f"{d.month}/{d.day}: 같은 날을 근무와 휴무로 함께 저장할 수 없습니다")
    with get_dash_engine().begin() as conn:
        w = _worker(conn, wid)
        targets: list[tuple[int, date]] = []
        for lid in dict.fromkeys(delete_ids):
            row = conn.execute(text("""SELECT work_date FROM work_logs
                WHERE id = :i AND worker_id = :w AND deleted_at IS NULL"""), {"i": lid, "w": wid}).fetchone()
            if not row:
                raise ValueError("삭제할 기록을 찾을 수 없습니다 (이미 수정·삭제됨 — 새로고침하세요)")
            if row[0] in days:
                raise ValueError(f"{row[0]}: 같은 날을 저장과 삭제에 함께 넣을 수 없습니다")
            targets.append((lid, row[0]))
        off_targets: list[tuple[int, date]] = []
        for oid in dict.fromkeys(off_delete_ids):
            row = conn.execute(text("""SELECT work_date FROM work_offs
                WHERE id = :i AND worker_id = :w AND deleted_at IS NULL"""), {"i": oid, "w": wid}).fetchone()
            if not row:
                raise ValueError("해제할 휴무를 찾을 수 없습니다 (이미 수정·삭제됨 — 새로고침하세요)")
            off_targets.append((oid, row[0]))
        touched = set(days) | set(off_days) | {d for _, d in targets} | {d for _, d in off_targets}
        for m in sorted({d.replace(day=1) for d in touched}):
            if _closed(conn, m):
                raise ValueError(f"{m.year}년 {m.month}월은 마감되었습니다. 마감 해제 후 수정하세요")
        for lid, _ in targets:
            conn.execute(text("UPDATE work_logs SET deleted_at = NOW(), deleted_by = :e WHERE id = :i"),
                         {"i": lid, "e": email})
            deleted += 1
        for oid, _ in off_targets:
            conn.execute(text("UPDATE work_offs SET deleted_at = NOW(), deleted_by = :e WHERE id = :i"),
                         {"i": oid, "e": email})
            off_deleted += 1
        for o in sorted(offs, key=lambda x: x["work_date"]):
            d = o["work_date"]
            try:
                off_saved += int(_write_off(conn, wid, o, email))
            except ValueError as e:
                raise ValueError(f"{d.month}/{d.day}: {e}") from None
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
    return {"ok": True, "saved": saved, "unchanged": unchanged, "deleted": deleted,
            "off_saved": off_saved, "off_deleted": off_deleted, "warns": warns}


def save_offs_bulk(d: date, ids: list[int], reason: str | None, memo: str | None, email: str) -> dict:
    """하루 × 여러 사람 휴무 지정(reason) / 해제(None). 한 트랜잭션.
    근무 기록이 있는 사람은 건너뛰고 이름을 돌려줌 (근무 기록은 건드리지 않음)."""
    saved = released = unchanged = 0
    skipped: list[str] = []
    with get_dash_engine().begin() as conn:
        if _closed(conn, d):
            raise ValueError(f"{d.year}년 {d.month}월은 마감되었습니다. 마감 해제 후 수정하세요")
        for wid in dict.fromkeys(ids):
            name = _worker(conn, wid)[0]
            if reason is None:
                row = conn.execute(text("""SELECT id FROM work_offs
                    WHERE worker_id = :w AND work_date = :d AND deleted_at IS NULL"""), {"w": wid, "d": d}).fetchone()
                if row:
                    conn.execute(text("UPDATE work_offs SET deleted_at = NOW(), deleted_by = :e WHERE id = :i"),
                                 {"i": row[0], "e": email})
                    released += 1
                else:
                    unchanged += 1
                continue
            if conn.execute(text("""SELECT 1 FROM work_logs
                WHERE worker_id = :w AND work_date = :d AND deleted_at IS NULL"""), {"w": wid, "d": d}).fetchone():
                skipped.append(name)
                continue
            if _write_off(conn, wid, {"work_date": d, "reason": reason, "memo": memo}, email):
                saved += 1
            else:
                unchanged += 1
    return {"ok": True, "saved": saved, "released": released, "unchanged": unchanged, "skipped": skipped}


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


# ---------- S2-P4b-2 월 마감 ----------
def _closing_out(r: dict) -> dict:
    return {"id": r["id"], "closed_at": _iso(r.get("closed_at")), "closed_by": r.get("closed_by"),
            "memo": r.get("memo"), "reopened_at": _iso(r.get("reopened_at")),
            "reopened_by": r.get("reopened_by"), "reopen_reason": r.get("reopen_reason"),
            "summary": r.get("summary")}


def _short_days(days: list[int]) -> str:
    s = ", ".join(f"{d}일" for d in days[:8])
    return s + (f" 외 {len(days) - 8}일" if len(days) > 8 else "")


def close_check(month: date) -> dict:
    """마감 점검. error = 마감 차단, warn = 확인, info = 안내. 끝나지 않은 달은 어제까지 진행 현황."""
    first, last = month_bounds(month)
    t = today()
    rates = _group(dash_db.rows("SELECT * FROM worker_pay_rates WHERE deleted_at IS NULL"), "worker_id")
    logs = _group(dash_db.rows(SQL_LOGS + " ORDER BY work_date", {"a": first, "b": last}), "worker_id")
    offs = _group(dash_db.rows(SQL_OFFS, {"a": first, "b": last}), "worker_id")
    history = [_closing_out(r) for r in dash_db.rows(
        "SELECT * FROM month_closings WHERE month = :m ORDER BY closed_at DESC", {"m": first})]
    closed = any(h["reopened_at"] is None for h in history)
    ended = t > last
    end = min(last, t - timedelta(days=1))
    issues: list[dict] = []
    totals = {"people": 0, "days": 0, "paid_min": 0, "sheet_total": 0}

    def add(level: str, w: dict | None, day: int | None, msg: str) -> None:
        issues.append({"level": level, "worker_id": w["id"] if w else None,
                       "name": w["name"] if w else None, "day": day, "msg": msg})

    if not ended:
        nxt = last + timedelta(days=1)
        add("error", None, None, f"아직 끝나지 않은 달입니다 ({nxt.month}월 {nxt.day}일부터 마감 가능) — 아래는 어제까지 현황")
    for w in dash_db.rows(SQL_WORKERS):
        rs, mine, off = rates.get(w["id"], []), logs.get(w["id"], []), offs.get(w["id"], [])
        cands = _spans(rs, "effective_from", first, last)
        if not mine and not off and not (w["active"] and any(_hourly(c) for c in cands)):
            continue
        done = {lg["work_date"] for lg in mine} | {o["work_date"] for o in off}
        if w["active"]:
            miss = [d.day for d in (first + timedelta(days=i) for i in range((end - first).days + 1))
                    if d not in done and is_workday(effective_on(rs, d, "effective_from"), d)]
            if miss:
                add("error", w, miss[0], f"미입력 {len(miss)}일 ({_short_days(miss)}) — 근무 또는 휴무를 입력하세요")
        elif mine:
            add("info", w, None, f"비활성 인력 — 미입력 검사 제외 (기록 {len(mine)}일은 근무표에 포함)")
        bad = [lg["work_date"].day for lg in mine
               if not _hourly(effective_on(rs, lg["work_date"], "effective_from"))]
        if bad:
            add("error", w, bad[0], f"계약 없는 날 근무 {len(bad)}일 ({_short_days(bad)}) — 계약 시작일 확인")
        long = [lg["work_date"].day for lg in mine if _mins(lg["clock_out"]) - _mins(lg["clock_in"]) > 720]
        if long:
            add("warn", w, long[0], f"12시간 넘는 근무 {len(long)}일 ({_short_days(long)}) — 시각 오기 확인")
        s = month_summary(mine, rs)
        if s["days"]:
            totals["people"] += 1
            totals["days"] += s["days"]
            totals["paid_min"] += s["paid_min"]
            totals["sheet_total"] += int(s["pay"]["sheet"]["total"])
    return {"month": first.isoformat(), "closed": closed, "ended": ended,
            "can_close": not closed and not any(i["level"] == "error" for i in issues),
            "issues": issues, "totals": totals, "history": history}


def close_month(month: date, memo: str | None, email: str) -> dict:
    chk = close_check(month)
    if chk["closed"]:
        raise ValueError("이미 마감된 달입니다 (새로고침하세요)")
    errs = [i for i in chk["issues"] if i["level"] == "error"]
    if errs:
        parts = [(f"{i['name']}: " if i["name"] else "") + i["msg"] for i in errs[:3]]
        more = f" 외 {len(errs) - 3}건" if len(errs) > 3 else ""
        raise ValueError("마감할 수 없습니다 — " + " / ".join(parts) + more)
    try:
        with get_dash_engine().begin() as conn:
            conn.execute(text("""
                INSERT INTO month_closings (month, closed_by, memo, summary)
                VALUES (:m, :e, :memo, CAST(:s AS JSONB))
            """), {"m": month.replace(day=1), "e": email, "memo": memo, "s": json.dumps(chk["totals"])})
    except IntegrityError:
        raise ValueError("이미 마감된 달입니다 (새로고침하세요)") from None
    return {"ok": True, "totals": chk["totals"]}


def reopen_month(month: date, reason: str, email: str) -> dict:
    reason = (reason or "").strip()
    if len(reason) < 2:
        raise ValueError("해제 사유를 2자 이상 입력하세요")
    with get_dash_engine().begin() as conn:
        res = conn.execute(text("""
            UPDATE month_closings SET reopened_at = NOW(), reopened_by = :e, reopen_reason = :r
            WHERE month = :m AND reopened_at IS NULL
        """), {"m": month.replace(day=1), "e": email, "r": reason})
    if res.rowcount == 0:
        raise ValueError("마감되지 않은 달입니다 (새로고침하세요)")
    return {"ok": True}


# ---------- S2-P4a-2 근무표 엑셀 내보내기 ----------
SQL_EXTRAS = """SELECT worker_id, kind, SUM(amount) AS amount FROM worker_month_extras
                WHERE deleted_at IS NULL AND month = :m GROUP BY worker_id, kind"""
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _mins(t) -> int:
    return t.hour * 60 + t.minute


def _range(month: date, start: date | None, end: date | None) -> tuple[date, date, date]:
    first, last = month_bounds(month)
    a, b = start or first, end or last
    if not (first <= a <= b <= last):
        raise ValueError(f"기간은 {first.month}월 안에서 시작일 ≤ 종료일로 지정하세요 (근무표는 한 달 양식)")
    return first, a, b


def export_plan(month: date, start: date | None = None, end: date | None = None,
                ids: list[int] | None = None) -> dict:
    """다운로드 전 점검 + 엑셀에 들어갈 값. error가 있는 구분은 파일을 만들지 않음 (sheet=None error는 두 파일 모두 차단).
    대상 = 시급 계약자(근로소득 시급제·사업자·프리랜서). 월급제(정규직)는 제외.
    인센티브 칸 = 그 달 데일리 인센티브 지급액 + 특수 수당 (계정 → 사람, S2-P4c-2) + 월 수당 수기 입력분"""
    first, a, b = _range(month, start, end)
    full = (a, b) == month_bounds(first)
    rates = _group(dash_db.rows("SELECT * FROM worker_pay_rates WHERE deleted_at IS NULL"), "worker_id")
    logs = _group(dash_db.rows(SQL_LOGS + " ORDER BY work_date", {"a": a, "b": b}), "worker_id")
    extras: dict[int, dict[str, int]] = {}
    for e in dash_db.rows(SQL_EXTRAS, {"m": first}):
        extras.setdefault(e["worker_id"], {})[e["kind"]] = int(e["amount"] or 0)
    with get_dash_engine().connect() as conn:
        closed = _closed(conn, first)
    want = set(ids) if ids else None
    sheets: dict[str, list[dict]] = {"labor": [], "business": []}
    issues: list[dict] = []

    def add(level: str, sheet: str | None, name: str | None, msg: str) -> None:
        issues.append({"level": level, "sheet": sheet, "name": name, "msg": msg})

    incm = None
    try:
        from app.services.incentive_service import person_month   # 함수 안 import = 서비스 간 순환 import 방지
        incm = person_month(first)
    except Exception as e:  # noqa: BLE001
        add("error", None, None, f"인센티브를 불러오지 못해 근무표를 만들 수 없습니다 ({type(e).__name__}) — 잠시 후 다시 시도하세요")
    inc_people = incm["people"] if incm else {}

    for w in dash_db.rows(SQL_WORKERS):
        sheet = SHEET_OF.get(w["income_type"])
        if sheet is None or (want is not None and w["id"] not in want):
            continue
        name = w["name"]
        rs, mine = rates.get(w["id"], []), logs.get(w["id"], [])
        cands = _spans(rs, "effective_from", a, b)
        if cands and not any(_hourly(r) for r in cands):
            if want is not None:
                add("info", sheet, name, "정규직(월급제)은 근무표 대상이 아닙니다 — 인센티브는 인센티브 > 사람별에서 확인")
            continue
        pi = inc_people.get(w["id"], {})
        spans = [r for r in cands if _hourly(r)]
        if not mine and not (spans and (w["active"] or want is not None)):
            if pi.get("incentive") or pi.get("extras"):
                add("warn", sheet, name, "기간 안 근무 기록이 없는데 인센티브가 배정되어 빠집니다 (고정 계정·그날 계정 확인)")
            elif want is not None:
                add("warn", sheet, name, "기간 안에 근무 기록·시급 계약이 없어 제외")
            continue
        days: dict[int, dict] = {}
        amounts: list[int] = []
        ok_logs: list[dict] = []
        for lg in mine:
            wd = lg["work_date"]
            r = effective_on(rs, wd, "effective_from")
            if not _hourly(r):
                add("error", sheet, name, f"{wd.month}/{wd.day} 근무에 적용되는 시급 계약이 없습니다 (인력 > 계약 조건 시작일 확인)")
                continue
            days[wd.day] = {"in": _mins(lg["clock_in"]), "out": _mins(lg["clock_out"]),
                            "break": sheet_break(lg.get("break_min"), r)}
            amounts.append(int(r["amount"]))
            ok_logs.append(lg)
        rate = amounts[-1] if amounts else (int(spans[-1]["amount"]) if spans else 0)
        if rate <= 0:
            continue                                  # 위에서 error 등록됨
        base = month_summary(ok_logs, rs)["base"]
        pay_value = None
        if len(set(amounts)) > 1:
            pay_value = base
            add("warn", sheet, name, f"월 중 시급 변경({amounts[0]:,}→{amounts[-1]:,}원): "
                "시급 칸은 마지막 시급, 월급여 칸은 날짜별 시급 합계 값(수식 아님)")
        ex = extras.get(w["id"], {})
        manual, wk, other = ex.get("incentive", 0), ex.get("weekend", 0), ex.get("other", 0)
        daily, special = int(pi.get("incentive", 0)), int(pi.get("extras", 0))
        inc = daily + special + manual
        if manual:
            add("warn", sheet, name, f"월 수당에 수기 인센티브 {manual:,}원이 있어 시스템 금액 "
                f"{daily + special:,}원과 합산됩니다 — 중복 입력이 아닌지 확인")
        if pi.get("pending_days"):
            add("warn", sheet, name, f"고객사 수 미입력 {pi['pending_days']}일은 데일리 인센티브 0원으로 들어갑니다 "
                "(인센티브 > 일자별 입력에서 입력 후 다시 받기)")
        if other:
            add("warn", sheet, name, f"기타 수당 {other:,}원은 근무표에 칸이 없어 빠집니다")
        if (inc or wk) and not full:
            add("info", sheet, name, "인센티브·주말수당은 기간과 관계없이 그 달 금액이 들어갑니다")
        if not days:
            add("warn", sheet, name, "기간 안 근무 0일 — 빈 블록으로 들어갑니다")
        last = effective_on(rs, b, "effective_from")
        vat = bool(sheet == "business" and _hourly(last) and last.get("vat_applied"))
        note = schedule_note([(r["effective_from"], _hm(r["work_start"]), _hm(r["work_end"]), int(r["amount"]))
                              for r in spans])
        sheets[sheet].append({
            "worker_id": w["id"], "name": name, "active": bool(w["active"]), "rate": rate, "note": note,
            "days": days, "pay_value": pay_value, "incentive": inc, "weekend": wk, "vat": vat,
            "inc_daily": daily, "inc_extras": special, "inc_manual": manual,
            "work_days": len(days), "paid_min": sum(v["out"] - v["in"] - v["break"] for v in days.values()),
            "base": base, "sheet_total": pay_total(base, 0, inc + wk, vat)["total"],
        })
    if incm and want is None:
        un = incm["unassigned"]
        for u in un[:10]:
            d = date.fromisoformat(u["date"])
            what = "고객사 수 미입력" if u["pending"] and not u["amount"] else f"{u['amount']:,}원"
            add("warn", None, u["manager_name"], f"{d.month}/{d.day} 인센티브 {what} — {u['why']}")
        if len(un) > 10:
            add("warn", None, None, f"담당 인력 미확인 인센티브 외 {len(un) - 10}건")
    if b > today():
        add("warn", None, None, "오늘 이후 날짜가 포함되어 있습니다 (아직 입력되지 않은 날)")
    if not closed:
        add("info", None, None, "마감 전 기록입니다. 이후 수정되면 다시 받아야 합니다")
    return {"month": first.isoformat(), "start": a.isoformat(), "end": b.isoformat(), "closed": closed,
            "sheets": sheets, "issues": issues,
            "ok": {s: not any(i["level"] == "error" and i["sheet"] in (s, None) for i in issues) for s in sheets}}


def _fname(sheet: str, first: date, a: date, b: date, people: list[dict], ids, dept: str) -> str:
    tail = "" if (a, b) == month_bounds(first) else f"_{a.day}-{b.day}일"
    if ids:
        tail += f"_{people[0]['name']}" if len(people) == 1 else f"_{len(people)}명"
    return f"{SHEET_TITLE[sheet]}_{dept}_{first.month}월 근무시간표{tail}.xlsx"


def export_file(sheet: str, month: date, start: date | None = None, end: date | None = None,
                ids: list[int] | None = None) -> tuple[str, bytes, str]:
    """→ (파일명, 내용, MIME). all = 근로·사업 두 파일 zip (한쪽이 비면 xlsx 하나)."""
    if sheet not in ("labor", "business", "all"):
        raise ValueError("구분은 labor / business / all 입니다")
    first, a, b = _range(month, start, end)
    plan = export_plan(month, start, end, ids)
    targets = ["labor", "business"] if sheet == "all" else [sheet]
    errs = [i for i in plan["issues"] if i["level"] == "error" and (i["sheet"] in targets or i["sheet"] is None)]
    if errs:
        more = f" 외 {len(errs) - 5}건" if len(errs) > 5 else ""
        raise ValueError("근무표를 만들 수 없습니다 — " + " / ".join(
            (f"{e['name']}: " if e["name"] else "") + e["msg"] for e in errs[:5]) + more)
    factory, dept = os.getenv("TIMESHEET_FACTORY", ""), os.getenv("TIMESHEET_DEPT", "물류팀")
    files: list[tuple[str, bytes]] = []
    for s in targets:
        people = plan["sheets"][s]
        if not people:
            continue
        data = build_timesheet(s, first, people, factory=factory, dept=dept)
        bad = verify_timesheet(data, people)
        if bad:
            raise ValueError(f"{SHEET_TITLE[s]} 파일 검증 실패로 중단 — " + " / ".join(bad[:5]))
        files.append((_fname(s, first, a, b, people, ids, dept), data))
    if not files:
        raise ValueError("내보낼 대상이 없습니다 (구분·인력·기간 확인)")
    if len(files) == 1:
        return files[0][0], files[0][1], XLSX
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in files:
            z.writestr(n, d)
    return f"{dept}_{first.month}월 근무시간표.zip", buf.getvalue(), "application/zip"
