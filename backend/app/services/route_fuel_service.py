"""S3-P2d-2a 물류비 화면의 참고 칸 — 날짜·계정별 NCP 예상 유류비 · 직접 계산(거리÷연비×오피넷 단가) · 주행거리.
실제 경로 구간(route_legs = 완료 순서대로 이은 실제 경로)만 쓴다. NAVER를 새로 부르지 않는다."""
from __future__ import annotations

from datetime import date

from app.services import dash_db
from app.services.cost_calc import latest_by
from app.services.route_fuel_calc import direct_cost, price_index, price_on


NCP_OK = ("gasoline", "diesel", "lpg")   # NAVER 유류비 지원 연료 (전기 제외)


def route_fuel(frm: date, to: date, assigns: list[dict]) -> tuple[dict[tuple[date, int], dict], list[str]]:
    """반환 = ({(날짜, 계정): {route_m, ncp, calc}}, 안내 문구). assigns = vehicle_assignments 행."""
    rows = dash_db.rows("""SELECT route_date, manager_id, SUM(distance_m) AS dist, SUM(fuel_price_naver) AS ncp,
            COUNT(*) FILTER (WHERE status = 'ok' AND ncp_mileage IS NULL) AS no_mileage,
            COUNT(*) FILTER (WHERE status = 'unreachable') AS bad
        FROM route_legs WHERE route_date BETWEEN :a AND :b
        GROUP BY route_date, manager_id HAVING SUM(distance_m) > 0""", {"a": frm, "b": to})
    if not rows:
        return {}, ["NCP 예상 유류비: 이 기간에 쌓인 실제 경로가 없어 참고 칸이 0원 (배송 완료 순서대로 3분마다 쌓임)"]
    vehicles = {r["id"]: r for r in dash_db.rows("SELECT id, fuel_type, fuel_efficiency FROM vehicles")}
    idx = price_index(dash_db.rows("""SELECT id, price_date, fuel_type, price, source FROM fuel_price_log
        WHERE deleted_at IS NULL AND price_date <= :b""", {"b": to}))
    assigned: dict[date, dict] = {}
    out: dict[tuple[date, int], dict] = {}
    no_calc = no_ncp = bad = 0
    for r in rows:
        d, mid = r["route_date"], int(r["manager_id"])
        if d not in assigned:
            assigned[d] = latest_by(assigns, "manager_id", "start_date", d)
        a = assigned[d].get(mid)
        v = vehicles.get(a["vehicle_id"]) if a and a.get("vehicle_id") else None
        dist = int(r["dist"])
        calc = direct_cost(dist, v["fuel_efficiency"], price_on(idx, v["fuel_type"], d)) if v else None
        if calc is None:
            no_calc += 1
        # 구간 계산 때 차량 연비를 넘긴 경우만 NCP 값을 씀 (NAVER 기본 연비 값은 쓰지 않음)
        ncp_ok = bool(v and v["fuel_type"] in NCP_OK and int(r["no_mileage"]) == 0)
        no_ncp += 0 if ncp_ok else 1
        bad += int(r["bad"])
        out[(d, mid)] = {"route_m": dist, "ncp": int(r["ncp"] or 0) if ncp_ok else 0, "calc": calc or 0}
    days = len({d for d, _ in out})
    notes = [f"NCP 예상 유류비: 실제 경로가 쌓인 {days}일 · {len(out)}건만 계산 (참고용, 물류비 합계에 넣지 않음)"]
    if no_calc:
        notes.append(f"직접 계산 유류비: {no_calc}건은 차량 미배정·연비 미입력·전기차·단가 없음으로 0원")
    if no_ncp:
        notes.append(f"NCP 예상 유류비: {no_ncp}건은 차량 미배정·연비 미입력(계산 당시)·전기차라 0원")
    if bad:
        notes.append(f"실제 경로: {bad}곳은 도로와 멀어 연결하지 못해 거리에서 빠짐")
    return out, notes
