"""S3-P2b 물류비 화면의 참고 칸 — 날짜·계정별 NCP 예상 유류비 · 직접 계산(거리÷연비×오피넷 단가) · 주행거리.
지도에서 계산·저장된 경로(route_cache)만 쓴다. NAVER를 새로 부르지 않는다."""
from __future__ import annotations

from datetime import date, timedelta

from app.services import dash_db
from app.services.cost_calc import latest_by
from app.services.route_fuel_calc import direct_cost, pick_routes, price_index, price_on


NCP_OK = ("gasoline", "diesel", "lpg")   # NAVER 유류비 지원 연료 (전기 제외)


def route_fuel(frm: date, to: date, assigns: list[dict]) -> tuple[dict[tuple[date, int], dict], list[str]]:
    """반환 = ({(날짜, 계정): {route_m, ncp, calc}}, 안내 문구). assigns = vehicle_assignments 행."""
    rows = dash_db.rows("""SELECT route_key, distance_m, fuel_price_naver, created_at FROM route_cache
        WHERE route_key >= :a AND route_key < :b AND distance_m > 0""",
                        {"a": frm.isoformat(), "b": (to + timedelta(days=1)).isoformat()})
    routes = pick_routes(rows)
    if not routes:
        return {}, ["NCP 예상 유류비: 이 기간에 저장된 경로가 없어 참고 칸이 0원 (지도에서 경로가 계산된 날만 표시)"]
    vehicles = {r["id"]: r for r in dash_db.rows("SELECT id, fuel_type, fuel_efficiency FROM vehicles")}
    idx = price_index(dash_db.rows("""SELECT id, price_date, fuel_type, price, source FROM fuel_price_log
        WHERE deleted_at IS NULL AND price_date <= :b""", {"b": to}))
    assigned: dict[date, dict] = {}
    out: dict[tuple[date, int], dict] = {}
    no_calc = 0
    no_ncp = 0    
    for (d, mid), r in routes.items():
        if d not in assigned:
            assigned[d] = latest_by(assigns, "manager_id", "start_date", d)
        a = assigned[d].get(mid)
        v = vehicles.get(a["vehicle_id"]) if a and a.get("vehicle_id") else None
        dist = int(r["distance_m"])
        calc = direct_cost(dist, v["fuel_efficiency"], price_on(idx, v["fuel_type"], d)) if v else None
        if calc is None:
            no_calc += 1
        # NAVER는 연비를 안 받으면 기본 연비로 계산 → 차량 연비가 있고 지원 연료일 때만 NCP 값을 씀
        ncp_ok = bool(v and v["fuel_efficiency"] and v["fuel_type"] in NCP_OK)
        no_ncp += 0 if ncp_ok else 1
        out[(d, mid)] = {"route_m": dist, "ncp": int(r["fuel_price_naver"] or 0) if ncp_ok else 0, "calc": calc or 0}
    days = len({d for d, _ in routes})
    notes = [f"NCP 예상 유류비: 경로가 저장된 {days}일 · {len(routes)}건만 계산 (참고용, 물류비 합계에 넣지 않음)"]
    if no_calc:
        notes.append(f"직접 계산 유류비: {no_calc}건은 차량 미배정·연비 미입력·전기차·단가 없음으로 0원")
    if no_ncp:
        notes.append(f"NCP 예상 유류비: {no_ncp}건은 차량 미배정·연비 미입력·전기차라 0원 (NAVER 기본 연비 값은 쓰지 않음)")        
    return out, notes
