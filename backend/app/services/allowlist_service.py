from sqlalchemy import text

from app.database import get_dash_engine


def list_allowlist() -> list[dict]:
    engine = get_dash_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, kind, value FROM auth_allowlist ORDER BY id")
        ).fetchall()
    return [{"id": r[0], "kind": r[1], "value": r[2]} for r in rows]


def add_allowlist(kind: str, value: str, added_by: str) -> None:
    engine = get_dash_engine()
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO auth_allowlist (kind, value, added_by) "
                "VALUES (:k, :v, :a) ON CONFLICT DO NOTHING"
            ),
            {"k": kind, "v": value, "a": added_by},
        )
        conn.commit()


def delete_allowlist(item_id: int) -> None:
    engine = get_dash_engine()
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM auth_allowlist WHERE id = :i"), {"i": item_id})
        conn.commit()
