"""S3-P2h-3d-2a 월별 정합성 표: 배송이 있던 날마다 계정 → 담당 인력 → 차량 (읽기 전용, 저장 없음).

- 판정은 물류비·유류비와 같은 assign_service.Assign 그대로 (표와 금액이 어긋나지 않게)
- 배송이 있던 (날짜, 계정)만 표시 — 배송 목록은 인센티브와 같은 fetch_stops_range (지난달은 Redis 캐시)
- 칸 표시 = assign_calc.board_flags (담당 인력 없음 · 퇴사 뒤 운행 · 차량 이력 없음 · 처분 뒤 사용 · 공유 차량)
- 담당 근거 = chosen(담당 지정) → log(근무 기록) → fixed(고정 계정), 인센티브 배정과 같은 순서
- 이력 겹침(계정·차량)은 달과 상관없이 전체 기준으로 함께 보여줌
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

from app.database import get_dash_engine
from app.services import dash_db
from app.services import worker_service as ws
from app.services import worker_vehicle_service as wv
from app.services.assign_calc import BOARD_ERRORS, BOARD_FLAGS, board_flags, overlaps
from app.services.assign_service import Assign

SQL_WORKERS = "SELECT id, name, end_date FROM workers WHERE deleted_at IS NULL"
SQL_CARS = "SELECT id, plate_no, disposed_on, active FROM vehicles WHERE deleted_at IS NULL"


def _month(month: str) -> tuple[date, date]:
    try:
        y, m = (int(x) for x in month.split("-"))
        s = date(y, m, 1)
    except (ValueError, TypeError):
        raise ValueError("월은 YYYY-MM 형식으로 지정하세요 (예: 2026-10)") from None
    return s, s.replace(day=calendar.monthrange(y, m)[1])


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _span(s: dict, workers: dict[int, dict]) -> dict:
    w = workers.get(s["worker_id"]) or {}
    return {"worker_id": s["worker_id"], "name": w.get("name"), "start": _iso(s["start"]), "end": _iso(s["end"])}


def _overlap_list(workers: dict[int, dict], cars: dict[int, dict], mgrs: dict[int, dict]) -> list[dict]:
    """계정·차량 이력 겹침 전체 (저장 검사와 같은 overlaps · 퇴사일 기준)"""
    out = []
    with get_dash_engine().connect() as c:
        ends = ws.worker_ends(c)
        groups = (("account", ws._acc_rows(c, None, None), "manager_id"),
                  ("vehicle", wv._hist_rows(c, None), "vehicle_id"))
        for kind, rows, key in groups:
            for o in overlaps(rows, ends, key):
                v = o["value"]
                if kind == "account":
                    label = (mgrs.get(v) or {}).get("name") or f"계정 {v}"
                else:
                    label = (cars.get(v) or {}).get("plate_no") or f"차량 {v}"
                out.append({"kind": kind, "value": v, "label": label, "from": _iso(o["from"]),
                            "first": _span(o["first"], workers), "second": _span(o["second"], workers)})
    return out


def board(month: str) -> dict:
    from app.services.incentive_service import _managers, fetch_stops_range   # 함수 안 import = 순환 import 방지
    s, e = _month(month)
    ran: dict[date, set[int]] = {}
    for r in fetch_stops_range(s, e):
        ran.setdefault(r["work_date"], set()).add(int(r["manager_id"]))
    a = Assign(s, e)
    chosen = {(k[0], int(k[1])) for k in a.ctx["chosen"]}
    logged = {(k[0], int(k[1])) for k in a.ctx["logged"]}
    workers = {int(w["id"]): w for w in dash_db.rows(SQL_WORKERS)}
    cars = {int(v["id"]): v for v in dash_db.rows(SQL_CARS)}
    mgrs = _managers()
    rows: dict[int, dict] = {}
    totals = {k: 0 for k in BOARD_FLAGS}
    used: set[int] = set()
    d = s
    while d <= e:
        mids = ran.get(d)
        if mids:
            day = a.day(d)
            shared = {m for ms in a.users(d).values() if len(ms) > 1 for m in ms}
            for mid in sorted(mids):
                r = day.get(mid) or {"worker_id": None, "vehicle_id": None, "basis": "unknown"}
                wid, vid = r.get("worker_id"), r.get("vehicle_id")
                w = workers.get(wid, {}) if wid is not None else {}
                car = cars.get(vid, {}) if vid else {}
                flags = board_flags(r, w.get("end_date"), car.get("disposed_on"), mid in shared, d)
                if wid is None:
                    src = None
                elif (d, mid) in chosen:
                    src = "chosen"
                elif (d, mid) in logged:
                    src = "log"
                else:
                    src = "fixed"
                m = mgrs.get(mid) or {}
                row = rows.setdefault(mid, {"manager_id": mid, "name": m.get("name") or f"계정 {mid}",
                                            "color": m.get("color"), "cells": {}, "run_days": 0,
                                            "counts": {k: 0 for k in BOARD_FLAGS}})
                row["cells"][str(d.day)] = {"worker_id": wid, "worker_name": w.get("name"), "vehicle_id": vid,
                                            "plate_no": car.get("plate_no"), "src": src, "basis": r.get("basis"),
                                            "flags": flags}
                row["run_days"] += 1
                for f in flags:
                    row["counts"][f] += 1
                    totals[f] += 1
                if vid:
                    used.add(int(vid))
        d += timedelta(days=1)
    unused = sorted(v["plate_no"] for k, v in cars.items()
                    if v["active"] and k not in used and (v["disposed_on"] is None or v["disposed_on"] >= s))
    items = sorted(rows.values(), key=lambda x: (-sum(x["counts"][k] for k in BOARD_ERRORS), x["name"]))
    return {"month": s.isoformat()[:7], "last_day": e.day, "flags": BOARD_FLAGS, "errors": list(BOARD_ERRORS),
            "rows": items, "totals": totals, "overlaps": _overlap_list(workers, cars, mgrs),
            "unused_vehicles": unused}
