"""S3-P2g-1 전기차 충전 단가 — 로밍 요금 매트릭스 업로드(미리보기 → 저장) · 삭제 · 예상 충전비 설정.

- 매트릭스에서 기후에너지환경부 카드 행만 저장 (사업자별 단가). 예상 충전비 기준은 그 행의 기후에너지환경부 충전기 단가
- 속도(완속·급속·초급속)·적용 시작일은 파일 이름에서 읽어 미리 채우고, 저장 전에 고칠 수 있다
- 같은 속도·같은 적용 시작일 단가가 이미 있으면 저장하지 않는다 (삭제 후 다시 올리기)
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from datetime import date

from sqlalchemy import text

from app.database import get_dash_engine
from app.services import dash_db
from app.services.ev_rate_calc import (MAX_BATCH, SPEED_LABEL, SPEEDS, batch_problems, guess_meta, parse_matrix,
                                       read_settings)
from app.services.fuel_excel import read_sheets

MAX_BYTES = 2 * 1024 * 1024


def _iso(v):
    return v.isoformat() if v is not None else None


def _decode(content_b64: str) -> bytes:
    s = (content_b64 or "").strip()
    if s.startswith("data:") and "," in s:
        s = s.split(",", 1)[1]
    try:
        data = base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("파일 내용을 읽을 수 없습니다") from exc
    if not data:
        raise ValueError("빈 파일입니다")
    if len(data) > MAX_BYTES:
        raise ValueError("파일이 너무 큽니다 (2MB 이하)")
    return data


def _parse(content_b64: str) -> tuple[bytes, dict]:
    data = _decode(content_b64)
    _, sheets = read_sheets(data)
    err: Exception | None = None
    for rows in sheets:
        try:
            return data, parse_matrix(rows)
        except ValueError as exc:
            err = exc
    raise ValueError(str(err) if err else "빈 파일입니다")


def _active(speed: str, eff: date) -> int | None:
    r = dash_db.rows("SELECT id FROM ev_rate_sets WHERE speed = :s AND effective_from = :d AND deleted_at IS NULL",
                     {"s": speed, "d": eff})
    return int(r[0]["id"]) if r else None


def preview(content_b64: str, file_name: str | None) -> dict:
    _, m = _parse(content_b64)
    meta = guess_meta(file_name)
    dup = _active(meta["speed"], meta["effective_from"]) if meta["speed"] and meta["effective_from"] else None
    return {"file_name": file_name, "issuer": m["issuer"], "base_operator": m["base_operator"],
            "base_price": m["base_price"], "header_row": m["header_row"], "rate_count": len(m["rates"]),
            "skipped": m["skipped"], "speed": meta["speed"], "effective_from": _iso(meta["effective_from"]),
            "duplicate_id": dup, "rates": m["rates"]}


def _insert(conn, data: bytes, m: dict, file_name: str | None, speed: str, effective_from: date,
            memo: str | None, email: str) -> int:
    """한 파일 저장 (트랜잭션 안에서). 같은 속도·같은 적용 시작일이 이미 있으면 ValueError → 묶음 전체 취소."""
    dup = conn.execute(text("SELECT id FROM ev_rate_sets WHERE speed = :s AND effective_from = :d "
                            "AND deleted_at IS NULL"), {"s": speed, "d": effective_from}).scalar()
    if dup:
        raise ValueError(f"{SPEED_LABEL[speed]} {effective_from.isoformat()} 단가가 이미 있습니다 (#{dup}) "
                         "— 목록에서 삭제한 뒤 다시 올리세요")
    sid = int(conn.execute(text("""
        INSERT INTO ev_rate_sets (speed, effective_from, issuer, base_price, rate_count, file_name, file_hash,
                                  memo, created_by)
        VALUES (:s, :d, :iss, :bp, :n, :fn, :h, :memo, :e) RETURNING id
    """), {"s": speed, "d": effective_from, "iss": m["issuer"][:100], "bp": m["base_price"],
           "n": len(m["rates"]), "fn": (file_name or "").strip()[:200] or None,
           "h": hashlib.sha256(data).hexdigest(), "memo": memo, "e": email}).scalar_one())
    conn.execute(text("INSERT INTO ev_rates (set_id, operator, price) VALUES (:sid, :op, :p)"),
                 [{"sid": sid, "op": r["operator"], "p": r["price"]} for r in m["rates"]])
    return sid


def commit(content_b64: str, file_name: str | None, speed: str, effective_from: date,
           memo: str | None, email: str) -> dict:
    if speed not in SPEEDS:
        raise ValueError("충전 속도를 선택하세요")
    data, m = _parse(content_b64)
    with get_dash_engine().begin() as conn:
        sid = _insert(conn, data, m, file_name, speed, effective_from, memo, email)
    return {"ok": True, "id": sid, "rate_count": len(m["rates"]), "base_price": m["base_price"]}


# ---------- S3-P2g-1d 여러 파일 한 번에 (최대 5개 · 속도마다 1개 · 전부 저장 또는 전부 취소) ----------
def preview_batch(files: list[dict]) -> list[dict]:
    """파일마다 미리보기. 읽지 못한 파일은 error에 이유를 담고 나머지는 계속 읽는다."""
    if not files:
        raise ValueError("올릴 파일이 없습니다")
    if len(files) > MAX_BATCH:
        raise ValueError(f"한 번에 {MAX_BATCH}개까지 올릴 수 있습니다 (지금 {len(files)}개)")
    out = []
    for f in files:
        try:
            out.append({**preview(f["content_b64"], f.get("file_name")), "error": None})
        except ValueError as exc:
            out.append({"file_name": f.get("file_name"), "error": str(exc)})
    return out


def commit_batch(items: list[dict], email: str) -> dict:
    parsed = []
    for it in items:
        try:
            data, m = _parse(it["content_b64"])
        except ValueError as exc:
            raise ValueError(f"{it.get('file_name') or '파일'}: {exc}") from exc
        parsed.append((it, data, m))
    problems = batch_problems([{"file_name": it.get("file_name"), "speed": it.get("speed"),
                                "effective_from": it.get("effective_from"),
                                "file_hash": hashlib.sha256(data).hexdigest()} for it, data, _ in parsed])
    if problems:
        raise ValueError(" / ".join(problems))
    saved = []
    with get_dash_engine().begin() as conn:      # 하나라도 실패하면 전부 되돌림
        for it, data, m in parsed:
            sid = _insert(conn, data, m, it.get("file_name"), it["speed"], it["effective_from"], it.get("memo"), email)
            saved.append({"id": sid, "speed": it["speed"], "rate_count": len(m["rates"]), "base_price": m["base_price"]})
    return {"ok": True, "saved": saved}


def get_settings() -> dict:
    return read_settings(dash_db.rows("SELECT key, value FROM cost_settings"))


def list_sets() -> dict:
    sets = dash_db.rows("""SELECT id, speed, effective_from, issuer, base_price, rate_count, file_name, memo,
            created_by, created_at
        FROM ev_rate_sets WHERE deleted_at IS NULL ORDER BY effective_from DESC, speed""")
    return {"settings": get_settings(),
            "sets": [{**s, "effective_from": _iso(s["effective_from"]), "base_price": float(s["base_price"]),
                      "created_at": _iso(s["created_at"])} for s in sets]}


def rates_of(sid: int) -> list[dict]:
    rows = dash_db.rows("""SELECT r.operator, r.price FROM ev_rates r JOIN ev_rate_sets s ON s.id = r.set_id
        WHERE r.set_id = :i AND s.deleted_at IS NULL ORDER BY r.id""", {"i": sid})
    if not rows:
        raise ValueError("단가 묶음을 찾을 수 없습니다")
    return [{"operator": r["operator"], "price": float(r["price"])} for r in rows]


def delete_set(sid: int, email: str) -> None:
    with get_dash_engine().begin() as conn:
        n = conn.execute(text("UPDATE ev_rate_sets SET deleted_at = NOW(), deleted_by = :e "
                              "WHERE id = :i AND deleted_at IS NULL"), {"e": email, "i": sid}).rowcount
    if n == 0:
        raise ValueError("대상을 찾을 수 없거나 이미 삭제되었습니다")


def save_settings(speed: str, km_per_kwh: float, email: str) -> dict:
    if speed not in SPEEDS:
        raise ValueError("충전 속도를 선택하세요")
    km = float(km_per_kwh)
    if not 0 < km <= 20:
        raise ValueError("기본 전비는 0보다 크고 20 이하(km/kWh)로 입력하세요")
    with get_dash_engine().begin() as conn:
        for k, v in (("ev_speed", speed), ("ev_km_per_kwh", f"{km:g}")):
            conn.execute(text("""
                INSERT INTO cost_settings (key, value, updated_by, updated_at) VALUES (:k, :v, :e, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by,
                                                updated_at = NOW()
            """), {"k": k, "v": v, "e": email})
    return get_settings()


def basis() -> tuple[dict, list[dict]]:
    """물류비 참고 칸용 = (설정, [{speed, effective_from, base_price}])."""
    sets = [{"speed": s["speed"], "effective_from": s["effective_from"], "base_price": float(s["base_price"])}
            for s in dash_db.rows("SELECT speed, effective_from, base_price FROM ev_rate_sets WHERE deleted_at IS NULL")]
    return get_settings(), sets
