-- S3-P2h-3d-5 배정 점검 제외 계정 (직원식·보류 등 일부러 담당을 비워 둔 계정). 표시만 바꾸고 인센티브·물류비 계산에는 쓰지 않음
-- 이 파일에는 콜론과 퍼센트 기호를 쓰지 않는다 (마이그레이션 실행기가 text() 사용)

CREATE TABLE IF NOT EXISTS board_excludes (
    id SERIAL PRIMARY KEY,
    manager_id INTEGER NOT NULL,
    reason VARCHAR(10) NOT NULL DEFAULT 'other' CHECK (reason IN ('internal', 'hold', 'other')),
    start_date DATE NOT NULL,
    end_date DATE,
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ,
    CHECK (end_date IS NULL OR end_date >= start_date)
);
CREATE INDEX IF NOT EXISTS ix_board_excludes_manager
    ON board_excludes (manager_id) WHERE deleted_at IS NULL;
