-- S2-P4c-1 인센티브 v2
-- 단가 구간표(적용 시작일 이력), 배송지 제외, 특수 수당(품목 목록), 미지급 여러 건
-- 이 파일에는 콜론과 퍼센트 기호를 쓰지 않는다 (마이그레이션 실행기가 text() 사용)

-- 1) 단가 구간표
CREATE TABLE IF NOT EXISTS incentive_rate_sets (
    id SERIAL PRIMARY KEY,
    effective_from DATE NOT NULL,
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_inc_rate_sets_from
    ON incentive_rate_sets (effective_from) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS incentive_rate_bands (
    id SERIAL PRIMARY KEY,
    set_id INTEGER NOT NULL REFERENCES incentive_rate_sets (id),
    kind VARCHAR(10) NOT NULL CHECK (kind IN ('product', 'account')),
    start_excl INTEGER NOT NULL CHECK (start_excl >= 0),
    end_incl INTEGER,
    amount INTEGER NOT NULL CHECK (amount >= 0),
    CHECK (end_incl IS NULL OR end_incl > start_excl)
);
CREATE INDEX IF NOT EXISTS ix_inc_rate_bands_set ON incentive_rate_bands (set_id);

-- 초기 단가표 = 기존 코드 값 (마지막 구간 끝값 비움 = 이상 전부)
INSERT INTO incentive_rate_sets (effective_from, memo, created_by)
SELECT DATE '2025-01-01', '초기 단가표 (기존 코드 값 이관)', 'migration'
WHERE NOT EXISTS (SELECT 1 FROM incentive_rate_sets);

INSERT INTO incentive_rate_bands (set_id, kind, start_excl, end_incl, amount)
SELECT s.id, v.kind, v.s, v.e, v.a
FROM incentive_rate_sets s
CROSS JOIN (VALUES
    ('product', 0, 300, 0), ('product', 300, 370, 50), ('product', 370, 440, 70), ('product', 440, NULL, 90),
    ('account', 0, 40, 0), ('account', 40, 45, 300), ('account', 45, 50, 400), ('account', 50, NULL, 500)
) AS v (kind, s, e, a)
WHERE s.created_by = 'migration'
  AND NOT EXISTS (SELECT 1 FROM incentive_rate_bands b WHERE b.set_id = s.id);

-- 2) 고객사 수 입력·제품 수 조정 (기존 표) — 고객사 수는 사유 없이 입력, 지우기는 삭제 표시
ALTER TABLE incentive_adjustments ALTER COLUMN reason DROP NOT NULL;
ALTER TABLE incentive_adjustments ADD COLUMN IF NOT EXISTS deleted_by VARCHAR(255);
ALTER TABLE incentive_adjustments ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS ix_adj_date_field ON incentive_adjustments (adj_date, field);

-- 3) 배송지 제외 (그 배송지 수량 전부 빼기)
CREATE TABLE IF NOT EXISTS incentive_exclusions (
    id SERIAL PRIMARY KEY,
    manager_id INTEGER NOT NULL,
    work_date DATE NOT NULL,
    address_id INTEGER NOT NULL,
    reason VARCHAR(20) NOT NULL CHECK (reason IN ('quick', 'other_manager', 'not_delivered', 'other')),
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_inc_excl
    ON incentive_exclusions (manager_id, work_date, address_id) WHERE deleted_at IS NULL;

-- 4) 특수 수당 품목 목록 + 날짜별 특수 수당 (인센티브 미지급과 무관하게 지급)
CREATE TABLE IF NOT EXISTS incentive_extra_items (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    unit_amount INTEGER CHECK (unit_amount IS NULL OR unit_amount > 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(255),
    updated_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_inc_extra_items_name ON incentive_extra_items (name);
INSERT INTO incentive_extra_items (name, sort_order, created_by)
VALUES ('오후 수거', 1, 'migration')
ON CONFLICT (name) DO NOTHING;

CREATE TABLE IF NOT EXISTS incentive_extras (
    id SERIAL PRIMARY KEY,
    manager_id INTEGER NOT NULL,
    work_date DATE NOT NULL,
    item_id INTEGER NOT NULL REFERENCES incentive_extra_items (id),
    item_name VARCHAR(50) NOT NULL,
    qty INTEGER NOT NULL CHECK (qty BETWEEN 1 AND 50),
    unit_amount INTEGER NOT NULL CHECK (unit_amount > 0),
    amount INTEGER NOT NULL CHECK (amount > 0),
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ,
    delete_reason TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_inc_extras
    ON incentive_extras (manager_id, work_date, item_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_inc_extras_date ON incentive_extras (work_date);

-- 5) 미지급 = 하루 여러 건 가능 (한 건이라도 남아 있으면 그날 인센티브 미지급), 해제 사유 기록
DO $$
DECLARE c TEXT;
BEGIN
    FOR c IN SELECT conname FROM pg_constraint
             WHERE conrelid = to_regclass('incentive_holds') AND contype = 'u'
    LOOP
        EXECUTE 'ALTER TABLE incentive_holds DROP CONSTRAINT ' || quote_ident(c);
    END LOOP;
END $$;
ALTER TABLE incentive_holds ADD COLUMN IF NOT EXISTS released_by VARCHAR(255);
ALTER TABLE incentive_holds ADD COLUMN IF NOT EXISTS release_reason TEXT;
CREATE INDEX IF NOT EXISTS ix_inc_holds_date ON incentive_holds (hold_date);
