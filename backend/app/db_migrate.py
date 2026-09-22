"""dash_db 마이그레이션 러너.
- backend/migrations/ 의 NNN_*.sql 을 번호 순서대로 적용
- 적용 이력은 schema_migrations 테이블에 기록 (중복 적용 없음)
- 배포 시 자동 실행: docker compose exec backend python -m app.db_migrate
"""
import logging
import os
from pathlib import Path

from sqlalchemy import text

from app.database import get_dash_engine

logger = logging.getLogger("migrate")
MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _ensure_table(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMPTZ DEFAULT NOW()
        )
    """))


def run() -> list[str]:
    if not MIGRATIONS_DIR.exists():
        logger.warning("migrations dir 없음: %s", MIGRATIONS_DIR)
        return []
    files = sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))
    engine = get_dash_engine()
    applied_now: list[str] = []
    with engine.connect() as conn:
        _ensure_table(conn)
        done = {r[0] for r in conn.execute(text("SELECT version FROM schema_migrations")).fetchall()}
        for name in files:
            if name in done:
                continue
            sql = (MIGRATIONS_DIR / name).read_text(encoding="utf-8")
            conn.execute(text(sql))
            conn.execute(text("INSERT INTO schema_migrations (version) VALUES (:v)"), {"v": name})
            conn.commit()
            applied_now.append(name)
            logger.info("applied: %s", name)
    print(f"migrations applied: {applied_now or 'none (up to date)'}")
    return applied_now


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
