"""S3-P2d-5 관제 제외 배송지 (dash_db.control_excludes).
지도·배송 집계·실제 경로(route_legs)에는 그대로 두고, 노선 관제(지연 예상·정체·예상 완료·남은 경로 미리보기)에서만 뺀다."""
from __future__ import annotations

from sqlalchemy import text

from app.database import get_dash_engine
from app.services import dash_db


def active_ids() -> set[int]:
    return {int(r["address_id"]) for r in dash_db.rows(
        "SELECT address_id FROM control_excludes WHERE deleted_at IS NULL")}


def list_items() -> list[dict]:
    rows = dash_db.rows("""SELECT id, address_id, label, memo, created_by, created_at FROM control_excludes
        WHERE deleted_at IS NULL ORDER BY label NULLS LAST, address_id""")
    return [{**r, "created_at": r["created_at"].isoformat() if r.get("created_at") else None} for r in rows]


def add(address_id: int, label: str | None, memo: str | None, email: str) -> int:
    with get_dash_engine().begin() as c:
        if c.execute(text("SELECT 1 FROM control_excludes WHERE address_id = :a AND deleted_at IS NULL"),
                     {"a": int(address_id)}).fetchone():
            raise ValueError("이미 관제 제외된 배송지입니다")
        return int(c.execute(text("""INSERT INTO control_excludes (address_id, label, memo, created_by)
            VALUES (:a, :l, :m, :e) RETURNING id"""),
            {"a": int(address_id), "l": (label or "").strip() or None, "m": (memo or "").strip() or None,
             "e": email}).scalar_one())


def remove(item_id: int, email: str) -> None:
    with get_dash_engine().begin() as c:
        n = c.execute(text("""UPDATE control_excludes SET deleted_at = NOW(), deleted_by = :e
            WHERE id = :i AND deleted_at IS NULL"""), {"i": int(item_id), "e": email}).rowcount
    if not n:
        raise ValueError("대상을 찾을 수 없거나 이미 해제되었습니다")
