-- S2-P4a-1 근무 기록 직접 입력. 지문 원시각, 그날 사용 계정, 월 마감
-- 중복 실행 안전

ALTER TABLE work_logs ADD COLUMN IF NOT EXISTS punch_in TIME;        -- 지문 출근 원시각 (비우면 지정 출근으로 봄)
ALTER TABLE work_logs ADD COLUMN IF NOT EXISTS manager_id INTEGER;   -- 그날 사용 운영 계정 (NULL = 고정 계정)
CREATE INDEX IF NOT EXISTS ix_work_logs_worker ON work_logs (worker_id, work_date);

CREATE TABLE IF NOT EXISTS month_closings (
    id SERIAL PRIMARY KEY,
    month DATE NOT NULL CHECK (EXTRACT(DAY FROM month) = 1),
    closed_by VARCHAR(255),
    closed_at TIMESTAMPTZ DEFAULT NOW(),
    reopened_by VARCHAR(255),
    reopened_at TIMESTAMPTZ,
    memo TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_month_closings_open
    ON month_closings (month) WHERE reopened_at IS NULL;
