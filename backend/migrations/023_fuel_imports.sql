-- S3-P1b-2b-3 주유 거래내역 엑셀 업로드 묶음 (한 번에 되돌리기 · 같은 파일 재업로드 경고)
-- 이 파일에는 콜론과 퍼센트 기호를 쓰지 않는다 (마이그레이션 실행기가 text() 사용)

-- 1) 업로드 묶음. 되돌리면 undone_at 기록 (이력 보존)
CREATE TABLE IF NOT EXISTS fuel_imports (
    id SERIAL PRIMARY KEY,
    file_name TEXT,
    file_hash CHAR(64) NOT NULL,
    date_from DATE NOT NULL,
    date_to DATE NOT NULL,
    log_count INTEGER NOT NULL,
    total_amount INTEGER NOT NULL,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    undone_by VARCHAR(255),
    undone_at TIMESTAMPTZ,
    undo_reason TEXT
);
CREATE INDEX IF NOT EXISTS ix_fuel_imports_hash ON fuel_imports (file_hash);
CREATE INDEX IF NOT EXISTS ix_fuel_imports_range ON fuel_imports (date_from, date_to);

-- 2) 주유 기록 ↔ 업로드 묶음 (직접 입력은 NULL)
ALTER TABLE fuel_logs ADD COLUMN IF NOT EXISTS import_id INTEGER REFERENCES fuel_imports(id);
CREATE INDEX IF NOT EXISTS ix_fuel_logs_import ON fuel_logs (import_id) WHERE import_id IS NOT NULL;
