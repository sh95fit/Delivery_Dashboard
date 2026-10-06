-- S2-P0 인력(사람) 분리: 급여·근무 기준은 사람 기준, 운영 계정(manager)은 고정 할당 + 일 단위 예외
-- manager_pay_rates는 화면 전환(S2-P0b)까지 유지, 이후 읽기 중단 (삭제하지 않음)

CREATE TABLE IF NOT EXISTS workers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    income_type VARCHAR(12) NOT NULL DEFAULT 'employee'
        CHECK (income_type IN ('regular', 'employee', 'business', 'freelancer')),
    vat_applied BOOLEAN NOT NULL DEFAULT FALSE,      -- 사업자: 지급액 + 부가세 10%
    active BOOLEAN NOT NULL DEFAULT TRUE,
    memo TEXT,
    legacy_manager_id INTEGER,                       -- 012 이전 데이터 연결용
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by VARCHAR(255),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ
);
-- 엑셀 이름 매칭 기준. 동명이인은 이름 뒤에 구분자를 붙여 등록
CREATE UNIQUE INDEX IF NOT EXISTS ux_workers_name ON workers (name) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS worker_pay_rates (
    id SERIAL PRIMARY KEY,
    worker_id INTEGER NOT NULL REFERENCES workers(id),
    pay_type VARCHAR(10) NOT NULL CHECK (pay_type IN ('monthly', 'hourly', 'none')),
    amount INTEGER NOT NULL DEFAULT 0 CHECK (amount >= 0),
    effective_from DATE NOT NULL,
    work_start TIME,
    work_end TIME,
    break_min INTEGER NOT NULL DEFAULT 0 CHECK (break_min BETWEEN 0 AND 600),
    break_paid BOOLEAN NOT NULL DEFAULT FALSE,
    ot_unit_min INTEGER NOT NULL DEFAULT 0 CHECK (ot_unit_min BETWEEN 0 AND 600),  -- 0 = 초과수당 없음
    ot_unit_amount INTEGER NOT NULL DEFAULT 0 CHECK (ot_unit_amount >= 0),
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_worker_rates_active
    ON worker_pay_rates (worker_id, effective_from) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS worker_accounts (
    id SERIAL PRIMARY KEY,
    worker_id INTEGER NOT NULL REFERENCES workers(id),
    manager_id INTEGER,                              -- 운영 manager.id, NULL = 고정 계정 없음
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
    worker_id INTEGER REFERENCES workers(id),        -- NULL = 그날 이 계정 미사용
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (work_date, manager_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_override_worker
    ON worker_account_overrides (work_date, worker_id) WHERE worker_id IS NOT NULL;

-- 기존 계정 기준 급여 → 사람 기준 이전 (이름은 화면에서 실제 이름으로 수정)
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
    (worker_id, pay_type, amount, effective_from, work_start, work_end,
     break_min, break_paid, memo, created_by, created_at)
SELECT w.id, p.pay_type, p.amount, p.effective_from, p.work_start, p.work_end,
       COALESCE(p.break_min, 0), COALESCE(p.break_paid, FALSE), p.memo, p.created_by, p.created_at
FROM manager_pay_rates p
JOIN workers w ON w.legacy_manager_id = p.manager_id
WHERE p.deleted_at IS NULL
  AND NOT EXISTS (
      SELECT 1 FROM worker_pay_rates x
      WHERE x.worker_id = w.id AND x.effective_from = p.effective_from AND x.deleted_at IS NULL);
