"""S3-P2h-1b 날짜별 계정 → 인력 → 차량 (DB 읽기 + 날짜별 결과 저장).

- 계정 → 인력: 인센티브 배정과 같은 함수 (incentive_service._owner = 담당 지정 → 근무 기록 → 고정 계정)
- 인력 → 차량: assign_calc.resolve (그날 예외 → 차량 이용 이력 → 없으면 기존 계정 차량 배정 vehicle_assignments)
- 퇴사일이 지난 인력은 차량 이력을 쓰지 않음 (기존 계정 차량 배정으로 넘어감)
- 쓰는 곳: 물류비(차량비·유류비·참고 칸), 유류비 월 집계(계정별 배분·초과 주행), 경로 계산 차량 정보
"""
from __future__ import annotations

from datetime import date

from app.services import dash_db
from app.services.assign_calc import group_by_worker, resolve, users_by_vehicle
from app.services.cost_calc import latest_by

SQL_HIST = "SELECT worker_id, start_date, mode, vehicle_id FROM worker_vehicles WHERE deleted_at IS NULL"
SQL_DAYS = """SELECT work_date, worker_id, vehicle_id FROM worker_vehicle_days
WHERE deleted_at IS NULL AND work_date BETWEEN :s AND :e"""
SQL_LEGACY = "SELECT manager_id, vehicle_id, start_date FROM vehicle_assignments WHERE deleted_at IS NULL"
SQL_ENDS = "SELECT id, end_date FROM workers WHERE deleted_at IS NULL AND end_date IS NOT NULL"


class Assign:
    """기간 s~e의 판정 재료를 한 번에 읽고, 날짜별 결과는 처음 물을 때 계산해 둔다."""

    def __init__(self, s: date, e: date):
        from app.services.incentive_service import _owner_ctx   # 함수 안 import = 순환 import 방지
        self.ctx = _owner_ctx(s, e)
        self.hist = group_by_worker(dash_db.rows(SQL_HIST))
        self.day_map = {(r["work_date"], int(r["worker_id"])): None if r["vehicle_id"] is None else int(r["vehicle_id"])
                        for r in dash_db.rows(SQL_DAYS, {"s": s, "e": e})}
        self.legacy_rows = dash_db.rows(SQL_LEGACY)
        self.ends = {int(r["id"]): r["end_date"] for r in dash_db.rows(SQL_ENDS)}
        self.mids_on: dict[date, set[int]] = {}
        for d, mid in list(self.ctx["logged"]) + list(self.ctx["chosen"]):
            self.mids_on.setdefault(d, set()).add(int(mid))
        self.basis: dict[str, int] = {}
        self._days: dict[date, dict[int, dict]] = {}

    def day(self, d: date) -> dict[int, dict]:
        """그날 {계정: {worker_id, vehicle_id, basis}}"""
        if d in self._days:
            return self._days[d]
        from app.services.incentive_service import _fixed_mid, _owner
        legacy = latest_by(self.legacy_rows, "manager_id", "start_date", d)
        mids = {int(m) for m in legacy} | self.mids_on.get(d, set())
        for wid in self.ctx["accs"]:
            m = _fixed_mid(self.ctx, wid, d)
            if m is not None:
                mids.add(m)
        out: dict[int, dict] = {}
        for mid in sorted(mids):
            owner = _owner(self.ctx, d, mid)[0]
            end = self.ends.get(owner) if owner is not None else None
            car_owner = None if end is not None and d > end else owner
            r = resolve(d, mid, car_owner, self.hist, self.day_map, legacy)
            out[mid] = {**r, "worker_id": owner}
            if r["vehicle_id"]:
                self.basis[r["basis"]] = self.basis.get(r["basis"], 0) + 1
        self._days[d] = out
        return out

    def users(self, d: date) -> dict[int, list[int]]:
        """그날 {차량: [계정, ...]} — 한 차량을 여러 계정이 쓰면 비용을 똑같이 나눔"""
        return users_by_vehicle(self.day(d))

    def vehicle(self, d: date, mid: int) -> int | None:
        return (self.day(d).get(int(mid)) or {}).get("vehicle_id")

    def notes(self) -> list[str]:
        n = self.basis.get("legacy", 0)
        if not n:
            return []
        return [f"차량: {n}건(계정×일)은 인력 차량 이용 이력이 없어 기존 계정 차량 배정으로 계산 — 인력 화면에서 차량 이용 이력을 넣으면 그 기준으로 바뀜"]


def vehicle_on(d: date, mid: int) -> int | None:
    """하루·계정 하나 (경로 계산용)."""
    return Assign(d, d).vehicle(d, mid)
