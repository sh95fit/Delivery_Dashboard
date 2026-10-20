"""S3-P1b-1 유가 계산 순수 함수 (DB 없음 → 단위 테스트 대상)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

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
        raw = str(o.get("TRADE_DT") or o.get("DATE") or "").strip()   # 현재가=TRADE_DT, 일별(7일) API=DATE
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


# ---------- S3-P2c 오피넷 확정 단가 채우기 · 유류비 기준 단가 ----------
def missing_chunks(have: set[date], frm: date, to: date) -> list[date]:
    """단가가 없는 날을 '특정 7일간'(기준일 포함 이전 7일) 요청으로 채울 기준일 목록. 최근 날짜부터."""
    ends, d = [], to
    while d >= frm:
        if d in have:
            d -= timedelta(days=1)
            continue
        ends.append(d)
        d -= timedelta(days=7)
    return ends


def ref_price(rows: list[dict], fuel_type: str, d: date, unit_price) -> dict:
    """주유일 기준 단가 (그날 없으면 바로 전 날짜, 같은 날은 직접 입력 우선). 차이(%) = 실제 단가 ÷ 기준 − 1."""
    p = price_on(rows, fuel_type, d)
    if not p:
        return {"ref_price": None, "ref_date": None, "ref_source": None, "ref_diff": None}
    price = float(p["price"])
    diff = round((float(unit_price) / price - 1) * 100, 1) + 0.0 if unit_price and price > 0 else None
    return {"ref_price": round(price, 2), "ref_date": p["price_date"].isoformat(),
            "ref_source": p["source"], "ref_diff": diff}


def add_basis(acc: dict, quantity, total, ref) -> None:
    """차량별 기준 단가 누적. 수량 있는 기록만. 오피넷 단가도 있는 기록은 비교용으로 따로 모음."""
    q = float(quantity or 0)
    if q <= 0:
        return
    acc["_q"] = acc.get("_q", 0.0) + q
    acc["_qt"] = acc.get("_qt", 0) + int(total)
    if ref:
        acc["_rq"] = acc.get("_rq", 0.0) + q
        acc["_rt"] = acc.get("_rt", 0) + int(total)
        acc["_ra"] = acc.get("_ra", 0.0) + q * float(ref)


def finish_basis(acc: dict) -> dict:
    """실제 평균 단가(합계÷수량) · 오피넷 평균(수량 가중) · 차이(%). 임시 키는 지움."""
    q, qt = acc.pop("_q", 0.0), acc.pop("_qt", 0)
    rq, rt, ra = acc.pop("_rq", 0.0), acc.pop("_rt", 0), acc.pop("_ra", 0.0)
    acc["avg_unit"] = round(qt / q, 2) if q else None
    acc["avg_ref"] = round(ra / rq, 2) if rq else None
    acc["ref_diff"] = round((rt / ra - 1) * 100, 1) + 0.0 if ra else None
    return acc
