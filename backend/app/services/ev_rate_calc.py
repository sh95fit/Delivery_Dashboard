"""S3-P2g-1 전기차 충전 단가 — 순수 함수 (DB 없음 → 단위 테스트 대상).

로밍 요금 매트릭스 (환경부 무공해차 누리집 내려받기 파일)
  행 = 카드 회원사(발급), 열 = 충전 사업자(이용), 칸 = 원/kWh, '-' = 로밍 없음
- 기후에너지환경부 카드 행만 읽는다. 예상 충전비 기준 = 그 행의 기후에너지환경부 충전기 칸
- 열 위치가 아니라 이름으로 찾는다 → 사업자가 늘거나 순서가 바뀌어도 동작
"""
from __future__ import annotations

import re
from datetime import date

SPEEDS = ("slow", "mid", "fast50", "fast100", "ultra")     # 느린 순 (대체 속도는 가까운 순으로 고름)
SPEED_LABEL = {"slow": "완속", "mid": "중속", "fast50": "급속 50~99kW", "fast100": "급속 100~199kW", "ultra": "초급속"}
LEGACY_SPEED = {"fast": "fast50"}                          # S3-P2g-1 시절 값
ISSUER_NAMES = ("기후에너지환경부", "환경부")
HEADER_SCAN = 20
MIN_OPERATORS = 3
MAX_PRICE = 2000
DEFAULT_SETTINGS = {"ev_speed": "fast50", "ev_km_per_kwh": 2.5}


def _key(v) -> str:
    return re.sub(r"\s+", "", str(v)) if v is not None else ""


def _is_issuer(k: str) -> bool:
    """'기후에너지환경부' · '환경부' · '기후에너지환경부(환경부)'처럼 괄호 표기도 인정 (한국자동차환경협회 등은 제외)."""
    return any(k == n or k.startswith(n + "(") for n in ISSUER_NAMES)


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
        if sum(1 for k in keys if k) >= MIN_OPERATORS and any(_is_issuer(k) for k in keys[1:]):
            h = i
            break
    if h is None:
        top = " / ".join(_key(v) for r in rows[:2] for v in r[:6] if _key(v))[:120]
        raise ValueError("요금 매트릭스 머리글(충전 사업자 이름 줄)을 찾지 못했습니다 — 로밍 요금 매트릭스 파일인지 확인하세요"
                         + (f" (읽힌 위쪽 내용: {top})" if top else " (읽힌 내용 없음)"))
    head = rows[h]
    keys = [_key(v) for v in head]
    first = next(j for j, k in enumerate(keys) if k)
    label_col = first - 1 if _is_issuer(keys[first]) and first > 0 else first

    ops: dict[int, str] = {}
    seen: set[str] = set()
    for j in range(label_col + 1, len(head)):
        k = keys[j]
        if k and k not in seen:
            ops[j] = str(head[j]).strip()[:100]
            seen.add(k)

    row = next((r for r in rows[h + 1:] if len(r) > label_col and _is_issuer(_key(r[label_col]))), None)

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
        if base is None and _is_issuer(_key(name)):
            base_op, base = name, p
    if base is None:
        raise ValueError("기후에너지환경부 충전기 단가 칸이 비어 있습니다 — 파일을 확인하세요")
    return {"issuer": _key(row[label_col]), "base_operator": base_op, "base_price": base,
            "header_row": h + 1, "rates": rates, "skipped": skipped}


def guess_meta(file_name: str | None) -> dict:
    """파일 이름 '로밍 요금 매트릭스(초급속(200kW 이상))_2026-10-22.xlsx' → {speed: 'ultra', effective_from: 2026-10-22}."""
    s = _key(file_name or "")
    speed = None
    if "초급속" in s:
        speed = "ultra"
    elif "중속" in s:
        speed = "mid"
    elif "완속" in s:
        speed = "slow"
    elif "급속" in s:                       # '급속(50~99kW)' · '급속(100~199kW)' → 앞 숫자로 구분, 숫자 없으면 직접 선택
        k = re.search(r"급속\(?(\d+)", s)
        if k:
            kw = int(k[1])
            speed = "fast100" if kw >= 100 else "fast50" if kw >= 50 else None
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
    i = SPEEDS.index(speed) if speed in SPEEDS else SPEEDS.index(DEFAULT_SETTINGS["ev_speed"])
    order = sorted(SPEEDS, key=lambda s: (abs(SPEEDS.index(s) - i), SPEEDS.index(s)))   # 설정 속도 → 가까운 속도 순
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
    """cost_settings 행 → {ev_speed, ev_km_per_kwh}. 값이 없거나 잘못되면 기본값 (급속 50~99kW · 2.5km/kWh, 주행 외 소모 포함)."""
    raw = {r["key"]: r["value"] for r in rows}
    out = dict(DEFAULT_SETTINGS)
    sp = LEGACY_SPEED.get(raw.get("ev_speed"), raw.get("ev_speed"))
    if sp in SPEEDS:
        out["ev_speed"] = sp
    try:
        km = float(raw.get("ev_km_per_kwh"))
        if 0 < km <= 20:
            out["ev_km_per_kwh"] = km
    except (TypeError, ValueError):
        pass
    return out
