"""S3-P2g-1 전기차 충전 단가 — 순수 함수 (DB 없음 → 단위 테스트 대상).

로밍 요금 매트릭스 (환경부 무공해차 누리집 내려받기 파일)
  행 = 카드 회원사(발급), 열 = 충전 사업자(이용), 칸 = 원/kWh, '-' = 로밍 없음
- 기후에너지환경부 카드 행만 읽는다. 예상 충전비 기준 = 그 행의 기후에너지환경부 충전기 칸
- 열 위치가 아니라 이름으로 찾는다 → 사업자가 늘거나 순서가 바뀌어도 동작
"""
from __future__ import annotations

import re
from datetime import date

SPEEDS = ("fast", "ultra", "slow")
SPEED_LABEL = {"fast": "급속", "ultra": "초급속", "slow": "완속"}
ISSUER_NAMES = ("기후에너지환경부", "환경부")
HEADER_SCAN = 20
MIN_OPERATORS = 3
MAX_PRICE = 2000
DEFAULT_SETTINGS = {"ev_speed": "fast", "ev_km_per_kwh": 3.1}


def _key(v) -> str:
    return re.sub(r"\s+", "", str(v)) if v is not None else ""


def _price(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        p = float(v)
    else:
        s = str(v).replace(",", "").replace("원", "").strip()
        try:
            p = float(s)
        except ValueError:
            return None
    return round(p, 2) if 0 < p <= MAX_PRICE else None


def parse_matrix(rows: list[list]) -> dict:
    """반환 = {issuer, base_operator, base_price, header_row, rates: [{operator, price}], skipped}."""
    h = None
    for i, r in enumerate(rows[:HEADER_SCAN]):
        keys = [_key(v) for v in r]
        if sum(1 for k in keys if k) >= MIN_OPERATORS and any(k in ISSUER_NAMES for k in keys[1:]):
            h = i
            break
    if h is None:
        raise ValueError("요금 매트릭스 머리글(충전 사업자 이름 줄)을 찾지 못했습니다 — 로밍 요금 매트릭스 파일인지 확인하세요")
    head = rows[h]
    keys = [_key(v) for v in head]
    first = next(j for j, k in enumerate(keys) if k)
    label_col = first - 1 if keys[first] in ISSUER_NAMES and first > 0 else first

    ops: dict[int, str] = {}
    seen: set[str] = set()
    for j in range(label_col + 1, len(head)):
        k = keys[j]
        if k and k not in seen:
            ops[j] = str(head[j]).strip()[:100]
            seen.add(k)

    row = None
    for name in ISSUER_NAMES:
        row = next((r for r in rows[h + 1:] if len(r) > label_col and _key(r[label_col]) == name), None)
        if row is not None:
            break
    if row is None:
        raise ValueError("기후에너지환경부 카드 행을 찾지 못했습니다 — 첫 칸에 '기후에너지환경부'가 있는 줄이 필요합니다")

    rates: list[dict] = []
    skipped = 0
    base_op, base = None, None
    for j, name in ops.items():
        p = _price(row[j]) if j < len(row) else None
        if p is None:
            skipped += 1
            continue
        rates.append({"operator": name, "price": p})
        if base is None and _key(name) in ISSUER_NAMES:
            base_op, base = name, p
    if base is None:
        raise ValueError("기후에너지환경부 충전기 단가 칸이 비어 있습니다 — 파일을 확인하세요")
    return {"issuer": _key(row[label_col]), "base_operator": base_op, "base_price": base,
            "header_row": h + 1, "rates": rates, "skipped": skipped}


def guess_meta(file_name: str | None) -> dict:
    """파일 이름 '로밍 요금 매트릭스(초급속(200kW 이상))_2026-10-22.xlsx' → {speed: 'ultra', effective_from: 2026-10-22}."""
    s = _key(file_name or "")
    speed = "ultra" if "초급속" in s else "fast" if "급속" in s else "slow" if "완속" in s else None
    eff = None
    m = re.search(r"(20\d{2})[-._]?(\d{2})[-._]?(\d{2})", s)
    if m:
        try:
            eff = date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            eff = None
    return {"speed": speed, "effective_from": eff}


def rate_on(sets: list[dict], speed: str, d: date) -> dict | None:
    """sets = [{speed, effective_from, base_price}]. 반환 = {price, speed, effective_from, early} 또는 None.
    1) 설정 속도에서 그날 이전 가장 최근 단가 2) 없으면 다른 속도 3) 그날 이전 단가가 전혀 없으면 가장 이른 단가(early=True)."""
    order = [speed] + [s for s in SPEEDS if s != speed]
    for sp in order:
        cand = [s for s in sets if s["speed"] == sp and s["effective_from"] <= d]
        if cand:
            best = max(cand, key=lambda s: s["effective_from"])
            return {"price": float(best["base_price"]), "speed": sp, "effective_from": best["effective_from"], "early": False}
    for sp in order:
        cand = [s for s in sets if s["speed"] == sp]
        if cand:
            best = min(cand, key=lambda s: s["effective_from"])
            return {"price": float(best["base_price"]), "speed": sp, "effective_from": best["effective_from"], "early": True}
    return None


def read_settings(rows: list[dict]) -> dict:
    """cost_settings 행 → {ev_speed, ev_km_per_kwh}. 값이 없거나 잘못되면 기본값 (급속 · 3.1km/kWh)."""
    raw = {r["key"]: r["value"] for r in rows}
    out = dict(DEFAULT_SETTINGS)
    if raw.get("ev_speed") in SPEEDS:
        out["ev_speed"] = raw["ev_speed"]
    try:
        km = float(raw.get("ev_km_per_kwh"))
        if 0 < km <= 20:
            out["ev_km_per_kwh"] = km
    except (TypeError, ValueError):
        pass
    return out
