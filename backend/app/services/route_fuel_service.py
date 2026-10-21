"""S3-P2d-3 물류비 화면의 참고 칸 — 날짜·계정별 NCP 예상 유류비 · 오피넷 기준(거리÷연비×오피넷 단가) · 주행거리 · 주행 시간.
실제 경로 구간(route_legs = 완료 순서대로 이은 실제 경로)만 쓴다. NAVER를 새로 부르지 않는다.
- NCP 예상 유류비: 차량 연비가 있으면 그 연비, 없으면 NAVER 기본 연비(14km/L) 기준 (중고 차량처럼 연비를 모를 때도 표시)
- 연비 입력 전에 쌓인 구간은 지금 입력된 연비로 환산 (route_fuel_calc.ncp_default)
- 주행 시간: NAVER 예상 운전 시간 합계 (배송지 정차 시간 제외)"""
from __future__ import annotations

from datetime import date

from app.services import dash_db
from app.services.cost_calc import latest_by
from app.services.route_fuel_calc import NAVER_DEFAULT_MILEAGE, direct_cost, ncp_scaled, price_index, price_on


NCP_OK = ("gasoline", "diesel", "lpg")   # NAVER 유류비 지원 연료 (전기 제외)


def route_fuel(frm: date, to: date, assigns: list[dict]) -> tuple[dict[tuple[date, int], dict], list[str]]:
    """반환 = ({(날짜, 계정): {route_m, route_ms, ncp, calc}}, 안내 문구). assigns = vehicle_assignments 행."""
    rows = dash_db.rows("""SELECT route_date, manager_id, SUM(distance_m) AS dist, SUM(duration_ms) AS dur,
            COALESCE(SUM(fuel_price_naver * COALESCE(ncp_mileage, CAST(:base AS NUMERIC))), 0) AS ncp_w,
            COUNT(*) FILTER (WHERE status = 'unreachable') AS bad
        FROM route_legs WHERE route_date BETWEEN :a AND :b
        GROUP BY route_date, manager_id HAVING SUM(distance_m) > 0""", {"a": frm, "b": to, "base": NAVER_DEFAULT_MILEAGE})
    if not rows:
        return {}, ["NCP 예상 유류비: 이 기간에 쌓인 실제 경로가 없어 참고 칸이 0원 (배송 완료 순서대로 3분마다 쌓임)"]
    vehicles = {r["id"]: r for r in dash_db.rows("SELECT id, fuel_type, fuel_efficiency FROM vehicles")}
    idx = price_index(dash_db.rows("""SELECT id, price_date, fuel_type, price, source FROM fuel_price_log
        WHERE deleted_at IS NULL AND price_date <= :b""", {"b": to}))
    assigned: dict[date, dict] = {}
    out: dict[tuple[date, int], dict] = {}
    no_calc = ev = default_n = scaled_n = bad = 0
    for r in rows:
        d, mid = r["route_date"], int(r["manager_id"])
        if d not in assigned:
            assigned[d] = latest_by(assigns, "manager_id", "start_date", d)
        a = assigned[d].get(mid)
        v = vehicles.get(a["vehicle_id"]) if a and a.get("vehicle_id") else None
        eff = v["fuel_efficiency"] if v else None
        dist = int(r["dist"])
        calc = direct_cost(dist, eff, price_on(idx, v["fuel_type"], d)) if v else None
        if calc is None:
            no_calc += 1
        if v and v["fuel_type"] not in NCP_OK:      # 전기차·연료 미지정 → NAVER 유류비 없음
            ncp = 0
            ev += 1
        else:                                       # [S3-P2e-2] 모든 구간을 지금 연비로 다시 산출 (구간 유류비 × 계산 당시 연비 ÷ 지금 연비)
            ncp = ncp_scaled(r["ncp_w"], eff)
            if eff:
                scaled_n += 1
            else:
                default_n += 1
        bad += int(r["bad"])
        out[(d, mid)] = {"route_m": dist, "route_ms": int(r["dur"] or 0), "ncp": ncp, "calc": calc or 0}
    days = len({d for d, _ in out})
    notes = [f"NCP 예상 유류비: 실제 경로가 쌓인 {days}일 · {len(out)}건 (참고용, 물류비 합계에 넣지 않음 · NAVER 경로 계산 시점의 전국 평균 유가 기준)"]
    if default_n:
        notes.append(f"NCP 예상 유류비: {default_n}건은 연비 미입력이라 NAVER 기본 연비(14km/L) 기준 — 차량에 연비를 넣으면 그 연비로 환산")
    if scaled_n:
        notes.append(f"NCP 예상 유류비: {scaled_n}건은 지금 차량 연비로 다시 산출 (연비를 넣거나 바꾸면 지난 날짜도 NAVER 재호출 없이 새 연비로 환산)")
    if ev:
        notes.append(f"NCP 예상 유류비: {ev}건은 전기차·연료 미지정이라 0원 (NAVER 미지원)")
    if no_calc:
        notes.append(f"오피넷 기준 유류비: {no_calc}건은 차량 미배정·연비 미입력·단가 없음(전기차는 전기 단가 직접 입력 필요)으로 0원")
    if bad:
        notes.append(f"실제 경로: {bad}곳은 도로와 멀어 연결하지 못해 거리에서 빠짐")
    notes.append("주행 시간: NAVER 예상 운전 시간 합계 (배송지 정차 시간 제외 · 지난 날짜 채우기는 채운 시점의 교통 기준)")
    return out, notes
