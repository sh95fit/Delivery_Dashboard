-- S2-P0b-2 보정. 012는 98b2991 판으로 운영에 적용된 뒤 내용이 바뀌어(256426c) 반영되지 않은 부분을 채움
-- 012 최신판으로 새로 만든 DB에서도 그대로 돌도록 모두 존재 확인 후 실행 (중복 실행 안전)

-- 1) 부가세 여부는 계약 이력(적용 시작일)마다 관리
ALTER TABLE worker_pay_rates ADD COLUMN IF NOT EXISTS vat_applied BOOLEAN NOT NULL DEFAULT FALSE;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = current_schema() AND table_name = 'workers' AND column_name = 'vat_applied') THEN
        EXECUTE 'UPDATE worker_pay_rates r SET vat_applied = TRUE
                 FROM workers w WHERE w.id = r.worker_id AND w.vat_applied AND NOT r.vat_applied';
    END IF;
END $$;

-- 2) 휴게 기본값 유급 (코드는 항상 값을 넘기므로 기존 행 영향 없음)
ALTER TABLE worker_pay_rates ALTER COLUMN break_paid SET DEFAULT TRUE;

-- 3) 지정 퇴근 > 지정 출근
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = to_regclass('worker_pay_rates') AND contype = 'c'
                     AND position('work_end > work_start' in pg_get_constraintdef(oid)) > 0) THEN
        ALTER TABLE worker_pay_rates ADD CONSTRAINT ck_worker_rates_time
            CHECK (work_start IS NULL OR work_end IS NULL OR work_end > work_start);
    END IF;
END $$;

-- 4) 실제 근무 기록 (P4a 근무표 업로드 / 직접 입력)
CREATE TABLE IF NOT EXISTS timesheet_uploads (
    id SERIAL PRIMARY KEY,
    month DATE NOT NULL CHECK (EXTRACT(DAY FROM month) = 1),
    file_name VARCHAR(255),
    sheet_name VARCHAR(100),
    file_sha256 CHAR(64),
    people INTEGER NOT NULL DEFAULT 0,
    days INTEGER NOT NULL DEFAULT 0,
    issues JSONB,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS work_logs (
    id SERIAL PRIMARY KEY,
    worker_id INTEGER NOT NULL REFERENCES workers(id),
    work_date DATE NOT NULL,
    clock_in TIME NOT NULL,                           -- 인정 출근
    clock_out TIME NOT NULL,                          -- 지문 퇴근
    break_min INTEGER CHECK (break_min IS NULL OR break_min BETWEEN 0 AND 600),   -- NULL = 계약 휴게
    source VARCHAR(10) NOT NULL DEFAULT 'manual' CHECK (source IN ('excel', 'manual')),
    upload_id INTEGER REFERENCES timesheet_uploads(id),
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ,
    CHECK (clock_out > clock_in)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_work_logs_active
    ON work_logs (worker_id, work_date) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_work_logs_date ON work_logs (work_date);

CREATE TABLE IF NOT EXISTS worker_month_extras (
    id SERIAL PRIMARY KEY,
    worker_id INTEGER NOT NULL REFERENCES workers(id),
    month DATE NOT NULL CHECK (EXTRACT(DAY FROM month) = 1),
    kind VARCHAR(10) NOT NULL CHECK (kind IN ('incentive', 'weekend', 'other')),
    amount INTEGER NOT NULL,
    memo TEXT,
    source VARCHAR(10) NOT NULL DEFAULT 'manual' CHECK (source IN ('excel', 'manual')),
    upload_id INTEGER REFERENCES timesheet_uploads(id),
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_month_extras ON worker_month_extras (month, worker_id);
