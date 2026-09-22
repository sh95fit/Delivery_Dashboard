-- 인센티브 수기 조정 이력 + 미지급(hold)
CREATE TABLE IF NOT EXISTS incentive_adjustments (
    id SERIAL PRIMARY KEY,
    manager_id INTEGER NOT NULL,
    adj_date DATE NOT NULL,
    field VARCHAR(30) NOT NULL,      -- gajung_qty | mil_qty | collection_count | stops | accounts
    value INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_adj_mgr_date ON incentive_adjustments (manager_id, adj_date);

CREATE TABLE IF NOT EXISTS incentive_holds (
    id SERIAL PRIMARY KEY,
    manager_id INTEGER NOT NULL,
    hold_date DATE NOT NULL,
    reason TEXT NOT NULL,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    released_at TIMESTAMPTZ,
    UNIQUE(manager_id, hold_date)
);
