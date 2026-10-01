-- S0-P3.1 직원식 대상: 일감·식수는 포함, 매출에서만 제외 + 별도 표시
CREATE TABLE IF NOT EXISTS internal_targets (
    id SERIAL PRIMARY KEY,
    kind VARCHAR(10) NOT NULL CHECK (kind IN ('address', 'account')),
    target_id INTEGER NOT NULL,          -- RDS addresses.id 또는 accounts.id
    label VARCHAR(255),                  -- 등록 시점 이름 (RDS 조회 실패 시 표시용)
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_internal_targets_active
    ON internal_targets (kind, target_id) WHERE deleted_at IS NULL;
