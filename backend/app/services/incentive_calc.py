"""S2-P4c-1 인센티브 계산 순수 함수 (DB 없음 → 단위 테스트 대상).

구간표 = [{"start": 300, "end": 370, "amount": 50}, ...]   amount = 1개(1곳)당 원
- 구간은 start 초과 ~ end 이하. 마지막 구간만 end 비움(None) 가능 = start 초과 전부
- 초과 기준 = 단가가 0보다 큰 첫 구간의 start (현재 제품 300, 고객사 40)
- 인센티브 = (수량 − 초과 기준) × 수량이 들어간 구간의 단가
- 마지막 구간에 끝값이 있는데 수량이 넘으면 → 마지막 구간 단가 적용 + 경고
- 미지급은 데일리 인센티브만 0원. 특수 수당(extras)은 별도로 더함
"""
from __future__ import annotations

MAX_BANDS = 20
KIND_LABEL = {"product": "제품 수", "account": "고객사 수"}
OVER_MAX_MSG = "해당 구간에 지정된 단가가 없어 최대 구간 단가를 적용합니다"


def check_bands(kind: str, bands: list[dict]) -> list[dict]:
    """구간표 검사 → 시작값 순으로 정리해 돌려줌. 저장을 막는 사유는 ValueError (메시지 그대로 화면 표시)."""
    label = KIND_LABEL.get(kind, kind)
    if not bands:
        raise ValueError(f"{label} 구간을 1개 이상 입력하세요")
    if len(bands) > MAX_BANDS:
        raise ValueError(f"{label} 구간은 {MAX_BANDS}개까지 입력할 수 있습니다")
    rows = sorted(
        ({"start": int(b["start"]), "end": None if b.get("end") is None else int(b["end"]),
          "amount": int(b["amount"])} for b in bands),
        key=lambda b: b["start"],
    )
    if rows[0]["start"] != 0:
        raise ValueError(f"{label} 첫 구간은 0부터 시작해야 합니다 (지금 {rows[0]['start']})")
    for i, b in enumerate(rows):
        last = i == len(rows) - 1
        if b["amount"] < 0:
            raise ValueError(f"{label} 단가는 0원 이상이어야 합니다")
        if b["end"] is None:
            if not last:
                raise ValueError(f"{label} 끝값 비움(이상 전부)은 마지막 구간에만 쓸 수 있습니다 "
                                 f"({b['start']} 초과 구간)")
            continue
        if b["end"] <= b["start"]:
            raise ValueError(f"{label} {b['start']}~{b['end']} 구간은 끝값이 시작값보다 커야 합니다")
        if not last and rows[i + 1]["start"] != b["end"]:
            raise ValueError(f"{label} 구간이 끊기거나 겹칩니다 — {b['start']}~{b['end']} 다음 구간은 "
                             f"{b['end']}부터 시작해야 합니다 (지금 {rows[i + 1]['start']})")
    if all(b["amount"] == 0 for b in rows):
        raise ValueError(f"{label} 단가가 있는 구간이 없습니다")
    return rows


def threshold(bands: list[dict]) -> int:
    """초과 기준 = 단가가 있는 첫 구간의 시작값"""
    return next(b["start"] for b in bands if b["amount"] > 0)


def band_pay(q: int, bands: list[dict]) -> dict:
    """수량 q → {amount, excess(초과분), unit(적용 단가), over_max(마지막 구간 끝값 초과)}"""
    th = threshold(bands)
    if q <= th:
        return {"amount": 0, "excess": 0, "unit": 0, "over_max": False}
    for b in bands:
        if b["start"] < q and (b["end"] is None or q <= b["end"]):
            return {"amount": (q - th) * b["amount"], "excess": q - th, "unit": b["amount"], "over_max": False}
    last = bands[-1]
    return {"amount": (q - th) * last["amount"], "excess": q - th, "unit": last["amount"], "over_max": True}


def day_row(stops: list[dict], excluded: dict, delta: int, accounts: int | None, rate: dict | None,
            held: bool, extras_total: int, shared: set | frozenset = frozenset()) -> dict:
    """계정 하루 계산.
    stops: [{"address_id", "gajung_qty", "mil_qty", "dinner_qty"}]  excluded: {address_id: 제외 기록}
    delta: ± 조정  accounts: 입력한 고객사 수(None = 미입력)  rate: {"product": 구간, "account": 구간} 또는 None
    shared: 그날 '제외하지 않은' 계정 2곳 이상에 배정된 배송지 id"""
    gajung = mil = dinner = pilot = excl = 0
    here: set[int] = set()
    shared_left = False
    for s in stops:
        aid = int(s["address_id"])
        here.add(aid)
        g, m = int(s.get("gajung_qty") or 0), int(s.get("mil_qty") or 0)
        gajung += g
        mil += m
        dinner += int(s.get("dinner_qty") or 0)
        pilot += int(s.get("pilot_qty") or 0)
        if aid in excluded:
            excl += g + m
        elif aid in shared:
            shared_left = True
    auto = gajung + mil
    warns: list[str] = []
    orphan = len(set(excluded) - here)
    if orphan:
        warns.append(f"제외한 배송지 {orphan}곳이 이 계정 배정에 없습니다 (배정이 바뀌었는지 확인)")
    if shared_left:
        warns.append("다른 계정과 함께 배정된 배송지가 있습니다 — 실제로 처리하지 않은 계정에서 배송지를 제외하세요")
    raw = auto - excl + int(delta or 0)
    product_total = max(0, raw)
    if raw < 0:
        warns.append("조정 후 제품 수가 0보다 작아 0으로 계산했습니다")

    need_accounts = accounts is None and bool(stops)       # 배송이 없는 날(특수 수당만)은 입력 불필요
    has_rate = bool(rate and rate.get("product") and rate.get("account"))
    prod = acc = None
    if has_rate:
        prod = band_pay(product_total, rate["product"])
        if prod["over_max"]:
            warns.append(f"제품 수 {product_total} — {OVER_MAX_MSG} ({prod['unit']:,}원)")
        if not need_accounts:
            q = 0 if accounts is None else int(accounts)
            acc = band_pay(q, rate["account"])
            if acc["over_max"]:
                warns.append(f"고객사 수 {q} — {OVER_MAX_MSG} ({acc['unit']:,}원)")
    else:
        warns.append("적용할 단가표가 없습니다 (인센티브 > 단가표에서 적용 시작일 확인)")

    incentive = prod["amount"] + acc["amount"] if prod is not None and acc is not None else None
    if held:
        status, payable = "held", 0
    elif not has_rate:
        status, payable = "no_rate", None
    elif need_accounts:
        status, payable = "need_accounts", None
    else:
        status, payable = "ok", incentive
    extras_total = int(extras_total or 0)
    return {
        "stops": len(stops), "gajung_qty": gajung, "mil_qty": mil, "dinner_qty": dinner, "pilot_qty": pilot,
        "auto_qty": auto, "excluded_qty": excl, "delta": int(delta or 0), "product_total": product_total,
        "accounts": accounts,
        "product_incentive": prod["amount"] if prod else None, "product_unit": prod["unit"] if prod else None,
        "account_incentive": acc["amount"] if acc else None, "account_unit": acc["unit"] if acc else None,
        "incentive": incentive, "held": held, "payable": payable,
        "extras": extras_total, "total": (payable or 0) + extras_total,
        "status": status, "warns": warns,
    }
