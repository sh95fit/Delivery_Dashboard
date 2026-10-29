"""S1-P1 매니저(운영 계정) 마스터 — [S3-P2h-3a] 계정은 운영 배송 기록(배송지·완료 시각·매출)의 단위만 맡는다.
- 이름·색·운영 상태: 운영 DB manager (읽기 전용). 색이 없거나 형식이 틀리면 대시보드와 같은 대체 색
- 대시보드 상태·메모: dash_db manager_profiles
- 급여·계약 조건 = 인력 계약 조건, 계정 연결 = 인력 고정 계정 · 근무 기록 그날 계정 · 담당 지정,
  차량 = 그날 담당 인력의 차량 (assign_service). 계정에는 급여·차량을 저장하지 않는다
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import text

from app.database import get_dash_engine, get_engine
from app.services import dash_db
from app.services.cost_calc import latest_by
from app.services.day_aggregate import KST, manager_color

SQL_MANAGERS = "SELECT * FROM manager ORDER BY id"
_OPS_ACTIVE = {"active", "1", "true", "y", "yes"}
_OPS_INACTIVE = {"inactive", "0", "false", "n", "no", "stop", "stopped", "suspended", "disabled"}

# 이 계정을 고정 계정으로 가진 인력 (재직 중이거나 퇴사일이 아직 안 지난 인력)
SQL_HOLDERS = """
SELECT a.worker_id, a.manager_id, a.start_date, w.name
FROM worker_accounts a
JOIN workers w ON w.id = a.worker_id AND w.deleted_at IS NULL AND (w.active OR w.end_date >= :d)
WHERE a.deleted_at IS NULL
"""


def ops_status(raw, deleted_at) -> str:
    """운영 DB manager.status → active / inactive / deleted / unknown"""
    if deleted_at is not None:
        return "deleted"
    s = str(raw if raw is not None else "").strip().lower()
    if s in _OPS_ACTIVE:
        return "active"
    if s in _OPS_INACTIVE:
        return "inactive"
    return "unknown"


def today() -> date:
    return datetime.now(KST).date()


def _iso(v):
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def _hm(v):
    if v is None:
        return None
    return v.strftime("%H:%M") if hasattr(v, "strftime") else str(v)[:5]


def _rds_managers() -> list[dict]:
    with get_engine().connect() as conn:
        base = conn.execute(text(SQL_MANAGERS)).mappings().all()
    out = []
    for r in base:
        raw = r.get("status")
        out.append({
            "manager_id": int(r["id"]),
            "name": r.get("name"),
            "color": manager_color(r["id"], r.get("color")),
            "ops_status": ops_status(raw, r.get("deleted_at")),
            "ops_status_raw": None if raw is None else str(raw),
        })
    return out


def list_managers() -> list[dict]:
    d = today()
    base = _rds_managers()
    profiles = {r["manager_id"]: r for r in dash_db.rows(
        "SELECT manager_id, active, memo, updated_by, updated_at FROM manager_profiles")}
    holders: dict[int, list[str]] = {}
    for r in latest_by(dash_db.rows(SQL_HOLDERS, {"d": d}), "worker_id", "start_date", d).values():
        if r["manager_id"] is not None:
            holders.setdefault(int(r["manager_id"]), []).append(r["name"])
    for m in base:
        mid = m["manager_id"]
        p = profiles.get(mid) or {}
        # 대시보드에서 한 번도 저장하지 않았으면 운영 상태를 따른다
        m["active"] = bool(p["active"]) if "active" in p else m["ops_status"] == "active"
        m["memo"] = p.get("memo")
        m["updated_at"] = _iso(p.get("updated_at"))
        m["updated_by"] = p.get("updated_by")
        m["workers"] = sorted(holders.get(mid, []))   # [S3-P2h-3a] 오늘 기준 고정 사용 인력
    return base


def save_profile(mid: int, active: bool, memo: str | None, email: str) -> None:
    with get_dash_engine().begin() as conn:
        conn.execute(text("""
            INSERT INTO manager_profiles (manager_id, active, memo, updated_by, updated_at)
            VALUES (:m, :a, :memo, :e, NOW())
            ON CONFLICT (manager_id) DO UPDATE
               SET active = EXCLUDED.active, memo = EXCLUDED.memo,
                   updated_by = EXCLUDED.updated_by, updated_at = NOW()
        """), {"m": mid, "a": active, "memo": memo, "e": email})
