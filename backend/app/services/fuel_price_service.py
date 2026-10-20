"""S3-P1b-1 유가 기록 — 오피넷 평균가(휘발유·경유·LPG) 하루 1번 자동 수집 + 직접 입력(전기 충전 단가 등).
가격은 주유소·충전소 판매가 그대로(부가세 포함). 규칙은 fuel_calc 참고."""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta

import requests
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import get_dash_engine
from app.services import dash_db
from app.services.cost_calc import days_incl
from app.services.fuel_calc import FUEL_TYPES, UNIT, missing_chunks, opinet_params, parse_opinet, price_on
from app.services.fuel_log_calc import month_bounds
from app.services.manager_service import today

logger = logging.getLogger("fuel_price")
OPINET_ALL = "https://www.opinet.co.kr/api/avgAllPrice.do"
OPINET_SIDO = "https://www.opinet.co.kr/api/avgSidoPrice.do"
RETRY_SEC = 3600
MAX_DAYS = 400
_last_ok: date | None = None
_last_try: datetime | None = None


def _out(r: dict) -> dict:
    return {"id": r["id"], "price_date": r["price_date"].isoformat(), "fuel_type": r["fuel_type"],
            "price": float(r["price"]), "source": r["source"], "memo": r.get("memo"),
            "created_by": r.get("created_by")}


def fetch_opinet() -> int:
    """오피넷 평균가를 받아 저장. OPINET_SIDO(예 01=서울)가 있으면 시도 평균, 없으면 전국 평균.
    인증키 파라미터 이름은 code (opinet_params 참고)."""
    key = os.environ.get("OPINET_API_KEY", "").strip().strip('"').strip("'")
    if not key:
        raise ValueError("서버 .env에 OPINET_API_KEY가 없습니다")
    sido = os.environ.get("OPINET_SIDO", "").strip()
    resp = requests.get(OPINET_SIDO if sido else OPINET_ALL, params=opinet_params(key, sido), timeout=10)
    resp.raise_for_status()
    try:
        payload = resp.json()
    except ValueError as exc:
        raise ValueError(f"오피넷 응답을 읽지 못했습니다 (HTTP {resp.status_code}) — {resp.text.strip()[:200]}") from exc
    items = parse_opinet(payload, today())
    if not items:
        raise ValueError("오피넷이 빈 목록을 돌려줬습니다 — OPINET_API_KEY 값·승인 상태와 OPINET_SIDO 코드를 확인하세요. "
                         f"응답 앞부분 {' '.join(resp.text.split())[:120]}")
    memo = f"시도 {sido} 평균" if sido else "전국 평균"
    with get_dash_engine().begin() as conn:
        for it in items:
            conn.execute(text("""
                INSERT INTO fuel_price_log (price_date, fuel_type, price, source, memo, created_by)
                VALUES (:d, :f, :p, 'opinet', :m, 'opinet')
                ON CONFLICT (price_date, fuel_type, source) WHERE deleted_at IS NULL
                DO UPDATE SET price = EXCLUDED.price, memo = EXCLUDED.memo
            """), {"d": it["price_date"], "f": it["fuel_type"], "p": it["price"], "m": memo})
    return len(items)


def ensure_today() -> None:
    """수집기가 매 주기 부름. 하루 1번 성공하면 그날은 더 안 부르고, 실패하면 1시간 뒤 재시도."""
    global _last_ok, _last_try
    t, now = today(), datetime.now()
    if _last_ok == t or (_last_try and (now - _last_try).total_seconds() < RETRY_SEC):
        return
    _last_try = now
    n = fetch_opinet()
    _last_ok = t
    logger.info("opinet ok: %s건", n)
    try:
        r = fill_prices(t - timedelta(days=7), t - timedelta(days=1))
        if r["saved"]:
            logger.info("opinet 확정 단가 %s건 (최근 7일)", r["saved"])
    except Exception:  # noqa: BLE001
        logger.warning("opinet 확정 단가 수집 실패", exc_info=True)


def list_prices(frm: date, to: date) -> dict:
    if to < frm:
        raise ValueError("조회 종료일이 시작일보다 빠릅니다")
    if days_incl(frm, to) > MAX_DAYS:
        raise ValueError(f"조회 기간은 {MAX_DAYS}일 이내로 지정하세요")
    rows = dash_db.rows("""SELECT id, price_date, fuel_type, price, source, memo, created_by
        FROM fuel_price_log WHERE deleted_at IS NULL AND price_date <= :t
        ORDER BY price_date DESC, id DESC""", {"t": to})
    current = {ft: price_on(rows, ft, to) for ft in FUEL_TYPES}
    return {"from": frm.isoformat(), "to": to.isoformat(), "units": UNIT,
            "has_key": bool(os.environ.get("OPINET_API_KEY", "").strip()),
            "current": {k: (_out(v) if v else None) for k, v in current.items()},
            "items": [_out(r) for r in rows if r["price_date"] >= frm]}


def add_manual(d: date, fuel_type: str, price: float, memo: str | None, email: str) -> int:
    if fuel_type not in FUEL_TYPES:
        raise ValueError("연료 종류가 올바르지 않습니다")
    if not 0 < price <= 10000:
        raise ValueError("단가를 확인하세요 (원/L 또는 원/kWh)")
    try:
        return dash_db.insert_id("""
            INSERT INTO fuel_price_log (price_date, fuel_type, price, source, memo, created_by)
            VALUES (:d, :f, :p, 'manual', :m, :e) RETURNING id
        """, {"d": d, "f": fuel_type, "p": price, "m": memo, "e": email})
    except IntegrityError as exc:
        raise ValueError("같은 날짜·연료로 직접 입력한 단가가 이미 있습니다. 삭제 후 다시 입력하세요") from exc


def delete_manual(pid: int, email: str) -> None:
    r = dash_db.rows("SELECT source FROM fuel_price_log WHERE id = :i AND deleted_at IS NULL", {"i": pid})
    if not r:
        raise ValueError("단가를 찾을 수 없습니다")
    if r[0]["source"] != "manual":
        raise ValueError("오피넷 자동 수집 값은 삭제할 수 없습니다 (같은 날짜로 직접 입력하면 그 값이 우선)")
    dash_db.soft_delete("fuel_price_log", pid, email)


# ---------- S3-P2c 오피넷 확정 단가 채우기 (기간에 없는 날만 API 호출 → DB 저장) ----------
OPINET_DAILY_ALL = "https://www.opinet.co.kr/api/dateAvgRecentPrice.do"
OPINET_DAILY_AREA = "https://www.opinet.co.kr/api/dateAreaAvgRecentPrice.do"
MAX_FILL_CALLS = 60                  # 1번에 최대 60회(약 420일). 오피넷 일반 API 하루 한도 300회
CONFIRMED = " (확정)"                 # 7일 API 값 = 일 평균 확정. 당일 게시값(fetch_opinet)과 메모로 구분
_tried: dict[date, datetime] = {}    # 같은 기준일은 1시간 안에 다시 부르지 않음


def _save(items: list[dict], memo: str) -> int:
    if not items:
        return 0
    with get_dash_engine().begin() as conn:
        for it in items:
            conn.execute(text("""
                INSERT INTO fuel_price_log (price_date, fuel_type, price, source, memo, created_by)
                VALUES (:d, :f, :p, 'opinet', :m, 'opinet')
                ON CONFLICT (price_date, fuel_type, source) WHERE deleted_at IS NULL
                DO UPDATE SET price = EXCLUDED.price, memo = EXCLUDED.memo
            """), {"d": it["price_date"], "f": it["fuel_type"], "p": it["price"], "m": memo})
    return len(items)


def _have(frm: date, to: date) -> set[date]:
    """확정 단가를 이미 받은 날. 오피넷이 일부 유종을 안 준 날도 받은 날로 본다 (반복 호출 방지)."""
    rows = dash_db.rows("""SELECT DISTINCT price_date FROM fuel_price_log
        WHERE deleted_at IS NULL AND source = 'opinet' AND memo LIKE :c AND price_date BETWEEN :f AND :t""",
                        {"c": f"%{CONFIRMED}", "f": frm, "t": to})
    return {r["price_date"] for r in rows}


def fill_prices(frm: date, to: date, max_calls: int = MAX_FILL_CALLS) -> dict:
    """[frm, to]에서 확정 단가가 없는 날만 '특정 7일간 일일 평균'으로 받아 저장. 확정값은 어제까지."""
    to = min(to, today() - timedelta(days=1))
    if to < frm:
        return {"calls": 0, "saved": 0, "missing": []}
    if days_incl(frm, to) > MAX_DAYS:
        raise ValueError(f"조회 기간은 {MAX_DAYS}일 이내로 지정하세요")
    key = os.environ.get("OPINET_API_KEY", "").strip().strip('"').strip("'")
    if not key:
        raise ValueError("서버 .env에 OPINET_API_KEY가 없습니다")
    sido = os.environ.get("OPINET_SIDO", "").strip()
    memo = (f"시도 {sido} 평균" if sido else "전국 평균") + CONFIRMED
    now, calls, saved = datetime.now(), 0, 0
    for end in missing_chunks(_have(frm, to), frm, to):
        if calls >= max_calls:
            break
        last = _tried.get(end)
        if last and (now - last).total_seconds() < RETRY_SEC:
            continue
        _tried[end] = now
        params = {"out": "json", "code": key, "date": end.strftime("%Y%m%d")}
        if sido:
            params["area"] = sido
        resp = requests.get(OPINET_DAILY_AREA if sido else OPINET_DAILY_ALL, params=params, timeout=10)
        calls += 1
        resp.raise_for_status()
        try:
            payload = resp.json()
        except ValueError as exc:
            raise ValueError(f"오피넷 응답을 읽지 못했습니다 (HTTP {resp.status_code}) — {resp.text.strip()[:200]}") from exc
        saved += _save(parse_opinet(payload, end), memo)
    have = _have(frm, to)
    missing = [(frm + timedelta(days=i)).isoformat() for i in range(days_incl(frm, to))
               if frm + timedelta(days=i) not in have]
    return {"calls": calls, "saved": saved, "missing": missing}


def daily_prices(month: str) -> dict:
    """유류비 탭 '일자별 단가' — 빠진 날을 먼저 채운 뒤 그 달 날짜별 단가(같은 날은 직접 입력 우선)."""
    f, t = month_bounds(month)
    notes = []
    try:
        r = fill_prices(f, t)
        if r["missing"]:
            notes.append(f"오피넷 확정 단가가 없는 날 {len(r['missing'])}일 ({r['missing'][0]} ~ {r['missing'][-1]})"
                         " — 오피넷 제공 범위 밖이거나 응답 없음. 1시간 뒤 다시 시도합니다")
    except Exception as exc:  # noqa: BLE001
        logger.warning("오피넷 단가 채우기 실패", exc_info=True)
        notes.append(f"오피넷 단가 불러오기 실패 — 저장된 값만 표시합니다 ({exc})")
    rows = dash_db.rows("""SELECT price_date, fuel_type, price, source, memo FROM fuel_price_log
        WHERE deleted_at IS NULL AND price_date BETWEEN :f AND :t ORDER BY price_date, id""", {"f": f, "t": t})
    cells: dict[date, dict] = {}
    for r in rows:
        c = cells.setdefault(r["price_date"], {})
        if r["fuel_type"] not in c or r["source"] == "manual":
            c[r["fuel_type"]] = {"price": float(r["price"]), "source": r["source"],
                                 "confirmed": CONFIRMED in (r["memo"] or "")}
    last = min(t, today())
    days = [f + timedelta(days=i) for i in range(days_incl(f, last))] if last >= f else []
    sido = os.environ.get("OPINET_SIDO", "").strip()
    return {"month": f"{f.year}-{f.month:02d}", "area": sido or None, "units": UNIT, "notes": notes,
            "days": [{"date": d.isoformat(), **{ft: cells.get(d, {}).get(ft) for ft in FUEL_TYPES}} for d in days]}
