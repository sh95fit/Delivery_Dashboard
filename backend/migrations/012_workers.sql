-- S2-P0 인력(사람) 기준 급여·근무. 운영 계정(manager)은 고정 할당 + 일 단위 예외
-- manager_pay_rates는 화면 전환(S2-P0b)까지 유지 후 읽기 중단 (삭제하지 않음)

CREATE TABLE IF NOT EXISTS workers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    income_type VARCHAR(12) NOT NULL DEFAULT 'employee'
        CHECK (income_type IN ('regular', 'employee', 'business', 'freelancer')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    memo TEXT,
    legacy_manager_id INTEGER,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by VARCHAR(255),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_workers_name ON workers (name) WHERE deleted_at IS NULL;

-- 계약 조건 이력 (적용 시작일부터 다음 변경 전까지)
CREATE TABLE IF NOT EXISTS worker_pay_rates (
    id SERIAL PRIMARY KEY,
    worker_id INTEGER NOT NULL REFERENCES workers(id),
    effective_from DATE NOT NULL,
    pay_type VARCHAR(10) NOT NULL CHECK (pay_type IN ('monthly', 'hourly', 'none')),
    amount INTEGER NOT NULL DEFAULT 0 CHECK (amount >= 0),
    vat_applied BOOLEAN NOT NULL DEFAULT FALSE,
    work_start TIME,                                  -- 지정 출근
    work_end TIME,                                    -- 지정 퇴근
    break_min INTEGER NOT NULL DEFAULT 0 CHECK (break_min BETWEEN 0 AND 600),
    break_paid BOOLEAN NOT NULL DEFAULT TRUE,
    ot_unit_min INTEGER NOT NULL DEFAULT 0 CHECK (ot_unit_min BETWEEN 0 AND 600),   -- 0 = 초과수당 없음
    ot_unit_amount INTEGER NOT NULL DEFAULT 0 CHECK (ot_unit_amount >= 0),
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ,
    CHECK (work_start IS NULL OR work_end IS NULL OR work_end > work_start)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_worker_rates_active
    ON worker_pay_rates (worker_id, effective_from) WHERE deleted_at IS NULL;

-- 고정 계정 이력 + 그날만 예외
CREATE TABLE IF NOT EXISTS worker_accounts (
    id SERIAL PRIMARY KEY,
    worker_id INTEGER NOT NULL REFERENCES workers(id),
    manager_id INTEGER,                               -- 운영 manager.id, NULL = 고정 계정 없음
    start_date DATE NOT NULL,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_worker_accounts_active
    ON worker_accounts (worker_id, start_date) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS worker_account_overrides (
    work_date DATE NOT NULL,
    manager_id INTEGER NOT NULL,
    worker_id INTEGER REFERENCES workers(id),         -- NULL = 그날 이 계정 미사용
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (work_date, manager_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_override_worker
    ON worker_account_overrides (work_date, worker_id) WHERE worker_id IS NOT NULL;

-- 실제 근무 (엑셀 업로드 / 직접 입력)
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

-- 기존 계정 기준 급여 → 사람 기준 이전 (이름은 S2-P0b 화면에서 실제 이름으로 수정). 두 번 실행해도 중복 없음
INSERT INTO workers (name, legacy_manager_id, created_by)
SELECT '계정#' || r.manager_id, r.manager_id, 'migration-012'
FROM (SELECT DISTINCT manager_id FROM manager_pay_rates WHERE deleted_at IS NULL) r
WHERE NOT EXISTS (SELECT 1 FROM workers w WHERE w.legacy_manager_id = r.manager_id);

UPDATE workers w SET active = mp.active
FROM manager_profiles mp
WHERE mp.manager_id = w.legacy_manager_id AND w.created_by = 'migration-012';

INSERT INTO worker_accounts (worker_id, manager_id, start_date, created_by)
SELECT w.id, w.legacy_manager_id, MIN(p.effective_from), 'migration-012'
FROM workers w
JOIN manager_pay_rates p ON p.manager_id = w.legacy_manager_id AND p.deleted_at IS NULL
WHERE NOT EXISTS (SELECT 1 FROM worker_accounts a WHERE a.worker_id = w.id)
GROUP BY w.id, w.legacy_manager_id;

INSERT INTO worker_pay_rates
    (worker_id, effective_from, pay_type, amount, work_start, work_end,
     break_min, break_paid, memo, created_by, created_at)
SELECT w.id, p.effective_from, p.pay_type, p.amount, p.work_start, p.work_end,
       COALESCE(p.break_min, 0), COALESCE(p.break_paid, FALSE), p.memo, p.created_by, p.created_at
FROM manager_pay_rates p
JOIN workers w ON w.legacy_manager_id = p.manager_id
WHERE p.deleted_at IS NULL
  AND NOT EXISTS (SELECT 1 FROM worker_pay_rates x
                  WHERE x.worker_id = w.id AND x.effective_from = p.effective_from AND x.deleted_at IS NULL);
