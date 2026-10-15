"""S3-P1b-1 유가 계산 순수 함수 (DB 없음 → 단위 테스트 대상)."""
from __future__ import annotations

from datetime import date, datetime

FUEL_TYPES = ("gasoline", "diesel", "lpg", "ev")
UNIT = {"gasoline": "원/L", "diesel": "원/L", "lpg": "원/L", "ev": "원/kWh"}
# 오피넷 제품코드 → 차량 연료. 고급휘발유(B034)·실내등유(C004)는 쓰지 않음
OPINET_CODE = {"B027": "gasoline", "D047": "diesel", "K015": "lpg"}


def opinet_params(key: str, sido: str = "") -> dict:
    """오피넷 요청 파라미터. 인증키 이름은 code (공식 문서 표의 certkey로 보내면 승인된 키여도 빈 목록이 옴)."""
    p = {"out": "json", "code": key}
    if sido:
        p["sido"] = sido
    return p


def parse_opinet(payload, default_date: date) -> list[dict]:
    """오피넷 평균가 응답 → [{price_date, fuel_type, price}]. 날짜 없는 응답(시도별)은 default_date."""
    oil = ((payload or {}).get("RESULT") or {}).get("OIL") or []
    if isinstance(oil, dict):
        oil = [oil]
    out = []
    for o in oil:
        ft = OPINET_CODE.get(str(o.get("PRODCD") or "").strip())
        if not ft:
            continue
        raw = str(o.get("TRADE_DT") or "").strip()
        try:
            d = datetime.strptime(raw, "%Y%m%d").date() if raw else default_date
            price = float(str(o.get("PRICE") or "").replace(",", ""))
        except ValueError:
            continue
        if price > 0:
            out.append({"price_date": d, "fuel_type": ft, "price": round(price, 2)})
    return out


def price_on(rows: list[dict], fuel_type: str, d: date) -> dict | None:
    """d 이전(당일 포함) 가장 최근 단가. 같은 날짜면 직접 입력이 오피넷보다 우선."""
    best = None
    for r in rows:
        if r["fuel_type"] != fuel_type or r["price_date"] > d:
            continue
        key = (r["price_date"], r["source"] == "manual")
        if best is None or key > (best["price_date"], best["source"] == "manual"):
            best = r
    return best


def direct_fuel_cost(distance_m: int, efficiency: float | None, price: float | None) -> int | None:
    """직접 계산 유류비 = 거리(km) ÷ 연비 × 단가. 연비·단가가 없으면 None."""
    if not efficiency or not price or efficiency <= 0:
        return None
    return round(int(distance_m or 0) / 1000 / float(efficiency) * float(price))
