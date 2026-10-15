-- S3-P1b-2b 주유 기록과 유류비 월 마감
-- 이 파일에는 콜론과 퍼센트 기호를 쓰지 않는다 (마이그레이션 실행기가 text() 사용)

-- 1) 주유 기록. 합계 = 공급가액 + 부가세. 수량은 리터, 전기차는 kWh
CREATE TABLE IF NOT EXISTS fuel_logs (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    fuel_date DATE NOT NULL,
    fuel_type VARCHAR(10) NOT NULL CHECK (fuel_type IN ('gasoline', 'diesel', 'lpg', 'ev')),
    quantity NUMERIC(10, 3),
    unit_price NUMERIC(8, 2),
    total_amount INTEGER NOT NULL CHECK (total_amount > 0),
    supply_amount INTEGER NOT NULL CHECK (supply_amount >= 0),
    vat_amount INTEGER NOT NULL CHECK (vat_amount >= 0),
    station TEXT,
    memo TEXT,
    source VARCHAR(10) NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'excel')),
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ,
    CHECK (supply_amount + vat_amount = total_amount)
);
CREATE INDEX IF NOT EXISTS ix_fuel_logs_date ON fuel_logs (fuel_date) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_fuel_logs_vehicle ON fuel_logs (vehicle_id, fuel_date) WHERE deleted_at IS NULL;

-- 2) 유류비 월 마감. close_month는 그달 1일. 해제하면 released_at 기록 (이력 보존)
CREATE TABLE IF NOT EXISTS fuel_closings (
    id SERIAL PRIMARY KEY,
    close_month DATE NOT NULL,
    total_amount INTEGER NOT NULL,
    cost_amount INTEGER NOT NULL,
    log_count INTEGER NOT NULL,
    memo TEXT,
    closed_by VARCHAR(255),
    closed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    released_by VARCHAR(255),
    released_at TIMESTAMPTZ,
    release_reason TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_fuel_closing_month
    ON fuel_closings (close_month) WHERE released_at IS NULL;
