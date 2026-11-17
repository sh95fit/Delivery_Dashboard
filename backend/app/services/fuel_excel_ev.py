"""S3-P2g-2 전기차 충전 실제 결제 내역 엑셀 읽기 — 환경부 공공충전인프라 멤버십카드 이용요금 현황 양식.

양식 (이용요금 현황(기간).xlsx 기준)
  순번 | 충전사업자 | 충전소명 | 카드번호 | 차량번호 | 충전시작일시 | 충전종료일시 | 충전소요시간 |
  충전량(kWh) | 충전금액(원/kWh) | 결제금액(원/kWh) | 충전포인트(P) | 결제결과 | 결제일시 | 간편결제 메모
- 위쪽에 제목·총계 행이 있어도 머리글 행을 이름으로 찾는다 (열 위치·순서 무관)
- 결제결과가 '승인'인 행만 저장. 나머지는 건수만 보고
- 날짜 = 결제일시(없으면 충전시작일시), 충전량(kWh)=수량, 결제금액=합계 → 공급가·부가세는 기존 규칙(합계÷1.1)으로 분리
- 차량 매칭·행 판정·저장은 주유 거래내역과 같은 흐름(fuel_excel.judge)을 그대로 쓴다
"""
from __future__ import annotations

from app.services.fuel_excel import MAX_ROWS, NoHeader, _key, _txt, _num, _won, norm_code, parse_date


def header_row(rows: list[list]) -> int | None:
    """머리글 행에 차량번호·충전량·결제금액이 모두 있으면 이 양식이다."""
    for i, r in enumerate(rows[:20]):
        joined = " ".join(t for t in (_key(_txt(v)) for v in r) if t)
        if "차량번호" in joined and "충전량" in joined and "결제금액" in joined:
            return i
    return None


def is_ev_sheet(rows: list[list]) -> bool:
    return header_row(rows) is not None


def parse_rows(rows: list[list]) -> dict:
    h = header_row(rows)
    if h is None:
        raise NoHeader("환경부 이용요금 현황 양식(차량번호·충전량·결제금액)을 찾지 못했습니다")
    cols: dict[str, int] = {}
    for j, v in enumerate(rows[h]):
        t = _key(_txt(v))
        for name, frag in (("operator", "충전사업자"), ("station", "충전소명"), ("plate", "차량번호"),
                           ("start", "충전시작"), ("kwh", "충전량"), ("pay", "결제금액"),
                           ("pay_date", "결제일시"), ("result", "결제결과")):
            if frag in t and name not in cols:
                cols[name] = j
    items: list[dict] = []
    skipped = 0
    for i in range(h + 1, len(rows)):
        r = rows[i]
        if all(v is None for v in r):
            continue
        res = _txt(r[cols["result"]]) if "result" in cols else "승인"
        pay = _won(r[cols["pay"]]) if "pay" in cols else None
        if (res and res != "승인") or not pay:
            skipped += 1
            continue
        if len(items) >= MAX_ROWS:
            raise ValueError(f"충전 행이 {MAX_ROWS}행을 넘습니다 — 파일을 나눠 올리세요")
        raw = _txt(r[cols["pay_date"]] if "pay_date" in cols else r[cols["start"]])
        items.append({
            "row": i + 1, "code": norm_code(_txt(r[cols["plate"]])),
            "date": parse_date(raw[:10]) if raw else None, "date_raw": raw,
            "product": "전기 충전", "fuel_type": "ev",
            "quantity": _num(r[cols["kwh"]]) if "kwh" in cols else None,
            "supply": None, "vat": None, "total": pay,
        })
    total = sum(it["total"] or 0 for it in items)
    return {"items": items, "skipped": skipped,
            "checks": [{"level": "ok", "text": f"전기차 충전 내역 {len(items)}행 · 합계 {total:,}원 (승인 결제만)"}],
            "header_row": h + 1, "ev": True}


def parse_upload(data: bytes) -> dict:
    """엑셀 업로드 진입점: 환경부 충전 양식이면 충전 파서, 아니면 기존 주유 파서."""
    from app.services.fuel_excel import parse_file as parse_fuel, read_sheets
    kind, sheets = read_sheets(data)
    for rows in sheets:
        if is_ev_sheet(rows):
            out = parse_rows(rows)
            out["file_kind"] = kind
            return out
    return parse_fuel(data)
