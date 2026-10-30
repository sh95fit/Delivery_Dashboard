"""S3-P2h-2a 인력 차량 이용 이력 · 그날 예외 (조회 · 추가 · 수정 · 삭제).
판정은 assign_service / assign_calc. 여기서는 저장 규칙만:
- 회사 차량은 차량 필수, 자차·차량 없음은 차량 비움
- 같은 회사 차량을 두 사람이 겹치는 기간에 이력으로 쓰면 거절 (하루만 같이 쓰면 그날 예외로)
- 유류비 마감된 달에 걸리는 이력·예외는 추가·수정·삭제 불가 → 유류비 탭에서 마감 해제 후 수정
- 퇴사일 뒤 날짜는 거절 (계산에 쓰이지 않음)
- 수정 = 기존 행 삭제 표시 + 새 행 (변경 기록 보존)
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text

from app.database import get_dash_engine
from app.services.assign_calc import DAY_REASON_LABEL, MODE_LABEL, check_mode, disposal_problem, find_conflict, lock_until
from app.services.manager_service import _iso

SQL_HIST_ALL = "SELECT id, worker_id, start_date, mode, vehicle_id FROM worker_vehicles WHERE deleted_at IS NULL"


# ---------- 검사 ----------
def _worker(conn, wid: int) -> dict:
    w = conn.execute(text("SELECT id, name, end_date FROM workers WHERE id = :w AND deleted_at IS NULL"),
                     {"w": wid}).mappings().fetchone()
    if not w:
        raise ValueError("인력을 찾을 수 없습니다")
    return dict(w)


def _check_vehicle(conn, vid: int | None, d: date | None = None) -> None:
    if vid is None:
        return
    r = conn.execute(text("SELECT plate_no, disposed_on FROM vehicles WHERE id = :v AND deleted_at IS NULL"),
                     {"v": vid}).fetchone()
    if not r:
        raise ValueError("차량을 찾을 수 없습니다 (삭제된 차량)")
    if d is not None and r[1] is not None and d > r[1]:
        raise ValueError(f"{r[0]} 차량은 {r[1]}에 처분되어 {d}부터는 선택할 수 없습니다")


def _check_end(w: dict, d: date, what: str) -> None:
    if w.get("end_date") is not None and d > w["end_date"]:
        raise ValueError(f"퇴사일({w['end_date']}) 뒤 {what}입니다 — 퇴사일 이후는 계산에 쓰이지 않습니다")


def _check_lock(conn, d: date, what: str) -> None:
    end = lock_until([r[0] for r in conn.execute(text(
        "SELECT close_month FROM fuel_closings WHERE released_at IS NULL")).fetchall()])
    if end is not None and d <= end:
        raise ValueError(f"{end.year}년 {end.month}월까지 유류비가 마감되어 {d} {what} 추가·수정·삭제할 수 없습니다. "
                         f"{end + timedelta(days=1)} 이후 날짜로 입력하거나, 유류비 탭에서 마감 해제 후 수정하세요")


def _check_conflict(conn, skip_id: int | None, new_row: dict | None) -> None:
    """저장 후 상태(skip_id 행 빼고 new_row 넣음)에서 같은 회사 차량을 두 사람이 겹쳐 쓰면 거절."""
    rows = [dict(r) for r in conn.execute(text(SQL_HIST_ALL)).mappings().all() if r["id"] != skip_id]
    if new_row is not None:
        rows.append(new_row)
    ends = {int(r[0]): r[1] for r in conn.execute(text(
        "SELECT id, end_date FROM workers WHERE deleted_at IS NULL AND end_date IS NOT NULL")).fetchall()}
    disposed = {int(r[0]): r[1] for r in conn.execute(text(
        "SELECT id, disposed_on FROM vehicles WHERE deleted_at IS NULL AND disposed_on IS NOT NULL")).fetchall()}
    p = disposal_problem(rows, ends, disposed)
    if p:
        plate = conn.execute(text("SELECT plate_no FROM vehicles WHERE id = :v"), {"v": p["vehicle_id"]}).scalar()
        raise ValueError(f"이대로 저장하면 {plate or p['vehicle_id']} 차량을 처분일({p['disposed_on']}) 뒤에도 쓰는 것으로 계산됩니다. "
                         "처분일 다음 날부터의 이력(다른 차량·자차·차량 없음)을 먼저 추가하세요")    
    c = find_conflict(rows, ends)
    if not c:
        return
    a, b = c["workers"]
    names = {int(r[0]): r[1] for r in conn.execute(text("SELECT id, name FROM workers WHERE id IN (:a, :b)"),
                                                     {"a": a, "b": b}).fetchall()}
    plate = conn.execute(text("SELECT plate_no FROM vehicles WHERE id = :v"), {"v": c["vehicle_id"]}).scalar()
    raise ValueError(f"{c['from']}부터 {plate or c['vehicle_id']} 차량을 '{names.get(a, a)}'님과 '{names.get(b, b)}'님이 "
                     "같은 기간에 쓰게 됩니다. 앞사람의 이력을 먼저 바꾸세요 (다른 차량·자차·차량 없음). "
                     "하루만 같이 쓰면 '그날 예외'로 입력하세요")


def _prep(data: dict) -> tuple[date, str, int | None]:
    mode = data["mode"]
    vid = data.get("vehicle_id") if mode == "company" else None
    err = check_mode(mode, vid)
    if err:
        raise ValueError(err)
    return data["start_date"], mode, vid


def _insert_hist(conn, wid: int, d: date, mode: str, vid: int | None, memo: str | None, email: str) -> int:
    return int(conn.execute(text("""
        INSERT INTO worker_vehicles (worker_id, start_date, mode, vehicle_id, memo, created_by)
        VALUES (:w, :s, :m, :v, :memo, :e) RETURNING id
    """), {"w": wid, "s": d, "m": mode, "v": vid, "memo": memo, "e": email}).scalar_one())


# ---------- 조회 ----------
def list_vehicles(wid: int) -> dict:
    with get_dash_engine().connect() as conn:
        _worker(conn, wid)
        hist = conn.execute(text("""
            SELECT h.id, h.start_date, h.mode, h.vehicle_id, v.plate_no, h.memo, h.created_by
            FROM worker_vehicles h LEFT JOIN vehicles v ON v.id = h.vehicle_id
            WHERE h.worker_id = :w AND h.deleted_at IS NULL ORDER BY h.start_date DESC
        """), {"w": wid}).mappings().all()
        days = conn.execute(text("""
            SELECT d.id, d.work_date, d.vehicle_id, v.plate_no, d.reason, d.memo, d.created_by
            FROM worker_vehicle_days d LEFT JOIN vehicles v ON v.id = d.vehicle_id
            WHERE d.worker_id = :w AND d.deleted_at IS NULL ORDER BY d.work_date DESC
        """), {"w": wid}).mappings().all()
    return {
        "history": [{"id": r["id"], "start_date": _iso(r["start_date"]), "mode": r["mode"],
                     "mode_label": MODE_LABEL.get(r["mode"], r["mode"]), "vehicle_id": r["vehicle_id"],
                     "plate_no": r["plate_no"], "memo": r["memo"], "created_by": r["created_by"]} for r in hist],
        "days": [{"id": r["id"], "work_date": _iso(r["work_date"]), "vehicle_id": r["vehicle_id"],
                  "plate_no": r["plate_no"], "reason": r["reason"],
                  "reason_label": DAY_REASON_LABEL.get(r["reason"], r["reason"]),
                  "memo": r["memo"], "created_by": r["created_by"]} for r in days],
    }


# ---------- 차량 이용 이력 ----------
def add_history(wid: int, data: dict, email: str) -> int:
    d, mode, vid = _prep(data)
    with get_dash_engine().begin() as conn:
        w = _worker(conn, wid)
        _check_vehicle(conn, vid, d)
        _check_end(w, d, "시작일")
        _check_lock(conn, d, "시작 차량 이용 이력은")
        if conn.execute(text("SELECT 1 FROM worker_vehicles WHERE worker_id = :w AND start_date = :s "
                             "AND deleted_at IS NULL"), {"w": wid, "s": d}).fetchone():
            raise ValueError(f"{d}에 시작하는 차량 이용 이력이 이미 있습니다. 이력에서 그 행을 수정하세요")
        _check_conflict(conn, None, {"id": None, "worker_id": wid, "start_date": d, "mode": mode, "vehicle_id": vid})
        return _insert_hist(conn, wid, d, mode, vid, data.get("memo"), email)


def update_history(hid: int, data: dict, email: str) -> int:
    d, mode, vid = _prep(data)
    with get_dash_engine().begin() as conn:
        old = conn.execute(text("SELECT worker_id, start_date FROM worker_vehicles WHERE id = :h AND deleted_at IS NULL"),
                           {"h": hid}).fetchone()
        if not old:
            raise ValueError("차량 이용 이력을 찾을 수 없습니다 (이미 수정·삭제됨 — 새로고침하세요)")
        wid = int(old[0])
        w = _worker(conn, wid)
        _check_vehicle(conn, vid, d)
        _check_end(w, d, "시작일")
        _check_lock(conn, min(old[1], d), "시작 차량 이용 이력은")
        if conn.execute(text("SELECT 1 FROM worker_vehicles WHERE worker_id = :w AND start_date = :s "
                             "AND deleted_at IS NULL AND id <> :h"), {"w": wid, "s": d, "h": hid}).fetchone():
            raise ValueError(f"{d}에 시작하는 다른 차량 이용 이력이 이미 있습니다. 그 행을 수정하세요")
        _check_conflict(conn, hid, {"id": None, "worker_id": wid, "start_date": d, "mode": mode, "vehicle_id": vid})
        conn.execute(text("UPDATE worker_vehicles SET deleted_at = NOW(), deleted_by = :e WHERE id = :h"),
                     {"h": hid, "e": email})
        return _insert_hist(conn, wid, d, mode, vid, data.get("memo"), email)


def delete_history(hid: int, email: str) -> None:
    with get_dash_engine().begin() as conn:
        old = conn.execute(text("SELECT start_date FROM worker_vehicles WHERE id = :h AND deleted_at IS NULL"),
                           {"h": hid}).fetchone()
        if not old:
            raise ValueError("대상을 찾을 수 없거나 이미 삭제되었습니다")
        _check_lock(conn, old[0], "시작 차량 이용 이력은")
        _check_conflict(conn, hid, None)     # 지우면 앞 이력이 길어져 겹칠 수 있음
        conn.execute(text("UPDATE worker_vehicles SET deleted_at = NOW(), deleted_by = :e WHERE id = :h"),
                     {"h": hid, "e": email})


# ---------- 그날 예외 ----------
def add_day(wid: int, data: dict, email: str) -> int:
    d = data["work_date"]
    vid = data.get("vehicle_id")
    with get_dash_engine().begin() as conn:
        w = _worker(conn, wid)
        _check_vehicle(conn, vid, d)
        _check_end(w, d, "날짜")
        _check_lock(conn, d, "그날 예외는")
        if conn.execute(text("SELECT 1 FROM worker_vehicle_days WHERE worker_id = :w AND work_date = :d "
                             "AND deleted_at IS NULL"), {"w": wid, "d": d}).fetchone():
            raise ValueError(f"{d} 그날 예외가 이미 있습니다. 삭제한 뒤 다시 입력하세요")
        return int(conn.execute(text("""
            INSERT INTO worker_vehicle_days (work_date, worker_id, vehicle_id, reason, memo, created_by)
            VALUES (:d, :w, :v, :r, :memo, :e) RETURNING id
        """), {"d": d, "w": wid, "v": vid, "r": data.get("reason") or "other",
               "memo": data.get("memo"), "e": email}).scalar_one())


def delete_day(did: int, email: str) -> None:
    with get_dash_engine().begin() as conn:
        old = conn.execute(text("SELECT work_date FROM worker_vehicle_days WHERE id = :i AND deleted_at IS NULL"),
                           {"i": did}).fetchone()
        if not old:
            raise ValueError("대상을 찾을 수 없거나 이미 삭제되었습니다")
        _check_lock(conn, old[0], "그날 예외는")
        conn.execute(text("UPDATE worker_vehicle_days SET deleted_at = NOW(), deleted_by = :e WHERE id = :i"),
                     {"i": did, "e": email})
