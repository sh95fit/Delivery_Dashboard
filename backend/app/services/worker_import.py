"""S2-P0b-2 인력 일괄 등록: 근무표 엑셀 / 운영 계정 → 미리보기 → 확정(전부 또는 전무)."""
from __future__ import annotations

import base64
import binascii
import calendar
import re
from datetime import date
from io import BytesIO

from sqlalchemy import text

from app.database import get_dash_engine
from app.services import dash_db
from app.services.cost_calc import latest_by
from app.services.manager_service import _rds_managers, today
from app.services.timesheet_excel import parse_timesheet, schedule_ranges
from app.services.worker_calc import check_rate
from app.services.worker_service import account_holder, insert_account, insert_rate

MAX_BYTES = 2 * 1024 * 1024
SHARED_RE = re.compile(r"공용|테스트|test|관리자|admin", re.I)


def _decode(content_b64: str) -> bytes:
    try:
        data = base64.b64decode(content_b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("파일 내용을 읽을 수 없습니다") from exc
    if not data:
        raise ValueError("빈 파일입니다")
    if len(data) > MAX_BYTES:
        raise ValueError("파일이 너무 큽니다 (2MB 이하)")
    if not data.startswith(b"PK"):
        raise ValueError("xlsx 형식이 아닙니다 (.xls는 엑셀에서 .xlsx로 다시 저장한 뒤 올려 주세요)")
    return data


def _sheets(data: bytes) -> list[tuple[str, list]]:
    import openpyxl  # 지연 import: 다른 기능은 openpyxl 없이도 동작

    try:
        wb = openpyxl.load_workbook(BytesIO(data), data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("엑셀 파일을 열 수 없습니다 (암호·손상 여부 확인)") from exc
    try:
        return [(ws.title, [list(r) for r in ws.iter_rows(values_only=True)]) for ws in wb.worksheets]
    finally:
        wb.close()


def _mgr_by_name() -> dict[str, dict]:
    try:
        mgrs = _rds_managers()
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, dict] = {}
    for m in sorted(mgrs, key=lambda x: x["ops_status"] != "active"):
        n = (m["name"] or "").strip()
        if n and m["ops_status"] != "deleted" and n not in out:
            out[n] = m
    return out


def _row(p: dict, sheet: str, month: str, file_income: str, workers: dict, cur_rates: dict,
         mgrs: dict, seen: set) -> dict:
    name = (p["name"] or "").strip()
    rate = int(round(p["rate"])) if p["rate"] and p["rate"] > 0 else None
    ranges = schedule_ranges(p["schedule_note"])
    has_vat = p["vat_total"] is not None
    income = "business" if has_vat else ("freelancer" if file_income == "business" else "employee")
    flags: list[str] = []
    if not ranges:
        flags.append("시간대 칸을 읽지 못했습니다 → 지정 출퇴근 직접 입력")
    elif len(ranges) > 1:
        flags.append(f"시간대 {len(ranges)}개 ({p['schedule_note']}) → 첫 시간대로 채움, 변경분은 등록 후 계약 이력에 추가")
    if file_income == "business" and not has_vat:
        flags.append("부가세 열 값 없음 → 프리랜서(부가세 미적용)로 채움")

    status = "new"
    if not name:
        status = "invalid"
        flags.insert(0, "이름이 비어 있습니다")
    elif name in seen:
        status = "dup"
        flags.insert(0, "파일 안에 같은 이름이 이미 있습니다 (첫 번째만 등록)")
    elif name in workers:
        status = "exists"
        r = cur_rates.get(workers[name]["id"])
        if r and rate and int(r["amount"]) != rate:
            flags.insert(0, f"이미 등록됨 · 시스템 시급 {int(r['amount']):,}원 ≠ 엑셀 {rate:,}원 (근무표 업로드 때 다시 대조)")
        else:
            flags.insert(0, "이미 등록된 인력")
    elif rate is None:
        status = "invalid"
        flags.insert(0, "시급을 읽을 수 없습니다")
    if name:
        seen.add(name)

    m = mgrs.get(name)
    ws_, we_ = ranges[0] if ranges else (None, None)
    return {
        "sheet": sheet, "row": p["row"], "month": month, "name": name, "rate": rate,
        "note": p["schedule_note"], "days": len(p["days"]), "minutes": p["minutes"],
        "has_vat": has_vat, "income_type": income, "work_start": ws_, "work_end": we_,
        "status": status, "flags": flags,
        "manager_id": m["manager_id"] if m else None, "manager_name": m["name"] if m else None,
    }


def preview_excel(content_b64: str, file_income: str) -> dict:
    data = _decode(content_b64)
    workers = {w["name"]: w for w in dash_db.rows("SELECT id, name FROM workers WHERE deleted_at IS NULL")}
    all_rates = dash_db.rows("SELECT worker_id, effective_from, amount FROM worker_pay_rates WHERE deleted_at IS NULL")
    mgrs = _mgr_by_name()
    sheets, rows, seen = [], [], set()
    for title, cells in _sheets(data):
        res = parse_timesheet(cells, title)
        lv = [x["level"] for x in res["issues"]]
        skipped = res["month"] is None or not res["people"]
        sheets.append({
            "sheet": title, "month": res["month"], "people": len(res["people"]),
            "errors": lv.count("error"), "warns": lv.count("warn"), "skipped": skipped,
            "msg": res["issues"][0]["msg"] if skipped and res["issues"] else "",
        })
        if skipped:
            continue
        m0 = date.fromisoformat(res["month"])
        m_end = date(m0.year, m0.month, calendar.monthrange(m0.year, m0.month)[1])
        cur = latest_by(all_rates, "worker_id", "effective_from", m_end)
        for p in res["people"]:
            rows.append(_row(p, title, res["month"], file_income, workers, cur, mgrs, seen))
    if not rows:
        first = next((s["msg"] for s in sheets if s["msg"]), "")
        raise ValueError("근무표 양식 시트를 찾지 못했습니다 ('연월' 칸·날짜 행·출근/퇴근/휴게/합계 4행)"
                         + (f" — {first}" if first else ""))
    return {"sheets": sheets, "rows": rows}


def account_candidates() -> list[dict]:
    mgrs = _rds_managers()
    names = {w["name"] for w in dash_db.rows("SELECT name FROM workers WHERE deleted_at IS NULL")}
    acc = dash_db.rows("""
        SELECT a.worker_id, a.manager_id, a.start_date, w.name
        FROM worker_accounts a
        JOIN workers w ON w.id = a.worker_id AND w.deleted_at IS NULL AND w.active
        WHERE a.deleted_at IS NULL
    """)
    held = {r["manager_id"]: r["name"] for r in latest_by(acc, "worker_id", "start_date", today()).values()
            if r["manager_id"] is not None}
    out = []
    for m in mgrs:
        if m["ops_status"] != "active":
            continue
        name = (m["name"] or "").strip()
        if m["manager_id"] in held:
            st = "held"
        elif name in names:
            st = "exists"
        elif not name or SHARED_RE.search(name):
            st = "shared"
        else:
            st = "new"
        out.append({"manager_id": m["manager_id"], "name": name, "color": m["color"], "status": st,
                    "holder": held.get(m["manager_id"])})
    order = {"new": 0, "shared": 1, "exists": 2, "held": 3}
    return sorted(out, key=lambda x: (order[x["status"]], x["name"]))


def commit(rows: list[dict], email: str) -> dict:
    ids: list[int] = []
    with get_dash_engine().begin() as conn:
        names = {r[0] for r in conn.execute(text("SELECT name FROM workers WHERE deleted_at IS NULL")).fetchall()}
        for i, r in enumerate(rows, 1):
            name = (r.get("name") or "").strip()
            tag = f"{i}번째 '{name}'"
            if not name:
                raise ValueError(f"{i}번째 행: 이름이 비어 있습니다")
            if name in names:
                raise ValueError(f"{tag}: 같은 이름의 인력이 이미 있습니다")
            try:
                rate = check_rate(r["income_type"], r["rate"]) if r.get("rate") else None
            except ValueError as exc:
                raise ValueError(f"{tag}: {exc}") from exc
            wid = int(conn.execute(text("""
                INSERT INTO workers (name, income_type, active, memo, created_by, updated_by)
                VALUES (:n, :t, TRUE, :m, :e, :e) RETURNING id
            """), {"n": name, "t": r["income_type"], "m": r.get("memo"), "e": email}).scalar_one())
            names.add(name)
            if rate:
                insert_rate(conn, wid, rate, email)
            mid = r.get("manager_id")
            if mid is not None:
                start = r.get("account_from") or (rate["effective_from"] if rate else today())
                holder = account_holder(conn, wid, mid, start)
                if holder:
                    raise ValueError(f"{tag}: {start} 기준 '{holder}'님이 이 계정을 고정 사용 중입니다")
                insert_account(conn, wid, mid, start, email)
            ids.append(wid)
    return {"ok": True, "created": len(ids), "ids": ids}
