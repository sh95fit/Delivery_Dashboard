-- S2-P4b-1 근무 요일(계약 이력별) + 날짜별 휴무 기록
-- 중복 실행 안전

-- 1) 근무 요일 비트 (월=1 화=2 수=4 목=8 금=16 토=32 일=64). 기본 월~금 = 31, 기존 계약도 31
ALTER TABLE worker_pay_rates ADD COLUMN IF NOT EXISTS work_days SMALLINT NOT NULL DEFAULT 31;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = to_regclass('worker_pay_rates') AND conname = 'ck_worker_rates_days') THEN
        ALTER TABLE worker_pay_rates ADD CONSTRAINT ck_worker_rates_days CHECK (work_days BETWEEN 0 AND 127);
    END IF;
END $$;

-- 2) 휴무 기록 (관리용, 근무표 엑셀에는 넣지 않음)
CREATE TABLE IF NOT EXISTS work_offs (
    id SERIAL PRIMARY KEY,
    worker_id INTEGER NOT NULL REFERENCES workers(id),
    work_date DATE NOT NULL,
    reason VARCHAR(20) NOT NULL,
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_work_offs_active ON work_offs (worker_id, work_date) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_work_offs_date ON work_offs (work_date);
