"""S3-P1b-2b-3 주유 거래내역 엑셀 업로드.

미리보기(저장 안 함) → 행 선택·차량 지정 → 저장(한 트랜잭션, 하나라도 실패하면 전부 취소) → 묶음 되돌리기.
- 저장할 때 파일을 다시 받아 서버에서 처음부터 다시 판정 (미리보기 결과를 그대로 믿지 않음)
- 차량 지정은 끝번호 단위: {"3300": 차량 id} → 그 번호의 모든 행에 적용
- 같은 파일(SHA-256)을 다시 올리면 경고. 이미 저장된 행은 중복 의심으로 선택 해제
"""
from __future__ import annotations

import base64
import binascii
import hashlib

from sqlalchemy import text

from app.database import get_dash_engine
from app.services import dash_db
from app.services.day_aggregate import KST
from app.services.fuel_excel import judge, norm_code, parse_file
from app.services.fuel_log_calc import month_bounds
from app.services.manager_service import today

MAX_BYTES = 2 * 1024 * 1024


def _iso(v):
    return v.isoformat() if v is not None else None


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode(content_b64: str) -> bytes:
    s = (content_b64 or "").strip()
    if s.startswith("data:") and "," in s:
        s = s.split(",", 1)[1]
    try:
        data = base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("파일 내용을 읽을 수 없습니다") from exc
    if not data:
        raise ValueError("빈 파일입니다")
    if len(data) > MAX_BYTES:
        raise ValueError("파일이 너무 큽니다 (2MB 이하)")
    return data


def _vehicles() -> list[dict]:
    return dash_db.rows("SELECT id, plate_no, model, fuel_type, vat_deductible, active FROM vehicles "
                        "WHERE deleted_at IS NULL ORDER BY plate_no")


def _evaluate(content_b64: str, vehicle_map: dict | None):
    data = _decode(content_b64)
    parsed = parse_file(data)
    items = parsed["items"]
    if not items:
        raise ValueError("주유 행이 없습니다 — 양식(일자·차량·합계 머리글 아래 거래 행)을 확인하세요")
    vehicles = _vehicles()
    dates = [x["date"] for x in items if x["date"]]
    existing, closed = set(), set()
    if dates:
        f, t = min(dates), max(dates)
        existing = {(r["vehicle_id"], r["fuel_date"], int(r["total_amount"])) for r in dash_db.rows(
            "SELECT vehicle_id, fuel_date, total_amount FROM fuel_logs "
            "WHERE deleted_at IS NULL AND fuel_date BETWEEN :f AND :t", {"f": f, "t": t})}
        closed = {r["close_month"] for r in dash_db.rows(
            "SELECT close_month FROM fuel_closings WHERE released_at IS NULL AND close_month BETWEEN :f AND :t",
            {"f": f.replace(day=1), "t": t})}
    vmap = {norm_code(k): int(v) for k, v in (vehicle_map or {}).items() if v}
    rows = judge(items, vehicles, vmap, existing, closed, today())
    return data, parsed, rows, vehicles


def _row_out(r: dict) -> dict:
    return {
        "row": r["row"], "code": r["code"], "date": _iso(r["date"]), "date_raw": r["date_raw"],
        "product": r["product"], "fuel_type": r["fuel_type"], "quantity": r["quantity"],
        "unit_price": r["unit_price"], "total_amount": r["total_amount"], "supply_amount": r["supply_amount"],
        "vat_amount": r["vat_amount"], "cost": r["cost"], "vehicle_id": r["vehicle_id"], "plate_no": r["plate_no"],
        "auto": r["auto"], "candidates": r["candidates"], "level": r["level"], "selectable": r["selectable"],
        "checked": r["checked"], "messages": r["messages"], "pair": r.get("pair"),
    }


def preview(content_b64: str, file_name: str | None, vehicle_map: dict | None) -> dict:
    data, parsed, rows, vehicles = _evaluate(content_b64, vehicle_map)
    checks = list(parsed["checks"])
    for p in dash_db.rows("SELECT id, log_count, created_by, created_at FROM fuel_imports "
                          "WHERE file_hash = :h AND undone_at IS NULL ORDER BY id", {"h": _hash(data)}):
        when = p["created_at"].astimezone(KST).strftime("%Y-%m-%d %H:%M")
        checks.insert(0, {"level": "warn", "text": f"같은 파일을 {when}에 {p['created_by'] or '-'}님이 이미 올렸습니다 "
                                                     f"(업로드 #{p['id']}, {p['log_count']}건) — 이미 저장된 행은 중복 의심으로 선택 해제됩니다"})
    codes: dict[str, dict] = {}
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["level"]] = counts.get(r["level"], 0) + 1
        if r["level"] == "cancel":
            continue
        c = codes.setdefault(r["code"], {"code": r["code"], "rows": 0, "total": 0, "vehicle_id": r["vehicle_id"],
                                         "auto": r["auto"], "candidates": r["candidates"]})
        c["rows"] += 1
        c["total"] += r["total_amount"] or 0
    picked = [r for r in rows if r["checked"]]
    return {
        "file_name": file_name, "file_kind": parsed["file_kind"], "header_row": parsed["header_row"],
        "skipped": parsed["skipped"], "checks": checks, "counts": counts,
        "selected": {"count": len(picked), "total": sum(r["total_amount"] for r in picked),
                     "cost": sum(r["cost"] or 0 for r in picked)},
        "codes": sorted(codes.values(), key=lambda c: c["code"]),
        "vehicles": [{"id": v["id"], "plate_no": v["plate_no"], "model": v.get("model"), "fuel_type": v["fuel_type"],
                      "vat_deductible": bool(v["vat_deductible"]), "active": bool(v["active"])} for v in vehicles],
        "rows": [_row_out(r) for r in rows],
    }


def commit(content_b64: str, file_name: str | None, vehicle_map: dict | None,
           row_nums: list[int], email: str) -> dict:
    data, _, rows, _ = _evaluate(content_b64, vehicle_map)
    by_row = {r["row"]: r for r in rows}
    pick = []
    for n in sorted(set(row_nums)):
        r = by_row.get(n)
        if r is None:
            raise ValueError(f"{n}행은 주유 행이 아닙니다 — 미리보기를 다시 하세요")
        if not r["selectable"]:
            why = " / ".join(r["messages"]) or "저장할 수 없는 행"
            raise ValueError(f"{n}행은 저장할 수 없습니다 ({why}) — 미리보기를 다시 하세요")
        pick.append(r)
    if not pick:
        raise ValueError("저장할 행을 선택하세요")
    months = {r["date"].replace(day=1) for r in pick}
    total = sum(r["total_amount"] for r in pick)
    with get_dash_engine().begin() as conn:
        shut = sorted(m for m in conn.execute(text(
            "SELECT close_month FROM fuel_closings WHERE released_at IS NULL AND close_month BETWEEN :f AND :t"
        ), {"f": min(months), "t": max(months)}).scalars().all() if m in months)
        if shut:
            raise ValueError("마감된 달이 있습니다 (" + ", ".join(f"{m.year}-{m.month:02d}" for m in shut)
                             + ") — 마감 해제 후 다시 저장하세요")
        iid = int(conn.execute(text("""
            INSERT INTO fuel_imports (file_name, file_hash, date_from, date_to, log_count, total_amount, created_by)
            VALUES (:n, :h, :f, :t, :c, :tot, :e) RETURNING id
        """), {"n": (file_name or "").strip()[:200] or None, "h": _hash(data),
               "f": min(r["date"] for r in pick), "t": max(r["date"] for r in pick),
               "c": len(pick), "tot": total, "e": email}).scalar_one())
        for r in pick:
            conn.execute(text("""
                INSERT INTO fuel_logs (vehicle_id, fuel_date, fuel_type, quantity, unit_price, total_amount,
                                       supply_amount, vat_amount, memo, source, created_by, import_id)
                VALUES (:v, :d, :ft, :q, :u, :tot, :sup, :vat, :memo, 'excel', :e, :i)
            """), {"v": r["vehicle_id"], "d": r["date"], "ft": r["vehicle_fuel"], "q": r["quantity"],
                   "u": r["unit_price"], "tot": r["total_amount"], "sup": r["supply_amount"], "vat": r["vat_amount"],
                   "memo": (r["product"] or "")[:200] or None, "e": email, "i": iid})
    return {"ok": True, "import_id": iid, "created": len(pick), "total": total}


def list_imports(month: str) -> list[dict]:
    f, t = month_bounds(month)
    rows = dash_db.rows("""
        SELECT i.id, i.file_name, i.date_from, i.date_to, i.log_count, i.total_amount, i.created_by, i.created_at,
               i.undone_by, i.undone_at, i.undo_reason, COUNT(l.id) AS active_count
        FROM fuel_imports i
        LEFT JOIN fuel_logs l ON l.import_id = i.id AND l.deleted_at IS NULL
        WHERE i.date_from <= :t AND i.date_to >= :f
        GROUP BY i.id ORDER BY i.id DESC
    """, {"f": f, "t": t})
    return [{**r, "date_from": _iso(r["date_from"]), "date_to": _iso(r["date_to"]),
             "created_at": _iso(r["created_at"]), "undone_at": _iso(r["undone_at"]),
             "active_count": int(r["active_count"])} for r in rows]


def undo_import(iid: int, reason: str, email: str) -> dict:
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("되돌리기 사유를 입력하세요")
    with get_dash_engine().begin() as conn:
        imp = conn.execute(text("SELECT id, undone_at FROM fuel_imports WHERE id = :i FOR UPDATE"),
                           {"i": iid}).mappings().first()
        if not imp:
            raise ValueError("업로드 기록을 찾을 수 없습니다")
        if imp["undone_at"]:
            raise ValueError("이미 되돌린 업로드입니다")
        shut = conn.execute(text("""
            SELECT DISTINCT c.close_month FROM fuel_logs l
            JOIN fuel_closings c ON c.released_at IS NULL
                 AND c.close_month = CAST(date_trunc('month', l.fuel_date) AS DATE)
            WHERE l.import_id = :i AND l.deleted_at IS NULL ORDER BY c.close_month
        """), {"i": iid}).scalars().all()
        if shut:
            raise ValueError("마감된 달이 포함되어 있습니다 (" + ", ".join(f"{m.year}-{m.month:02d}" for m in shut)
                             + ") — 마감 해제 후 되돌리세요")
        n = conn.execute(text("UPDATE fuel_logs SET deleted_at = NOW(), deleted_by = :e "
                              "WHERE import_id = :i AND deleted_at IS NULL"), {"e": email, "i": iid}).rowcount
        conn.execute(text("UPDATE fuel_imports SET undone_at = NOW(), undone_by = :e, undo_reason = :r WHERE id = :i"),
                     {"e": email, "r": reason[:200], "i": iid})
    return {"ok": True, "deleted": n}
