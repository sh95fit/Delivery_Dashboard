-- S1-P1 매니저·차량 마스터, 기간 비용, 지출 내역 (dash_db)
-- 급여·차량 배정은 적용 시작일 이력. 삭제는 deleted_at 기록(소프트 삭제)

CREATE TABLE IF NOT EXISTS manager_profiles (
    manager_id INTEGER PRIMARY KEY,                 -- 운영 DB manager.id
    active BOOLEAN NOT NULL DEFAULT TRUE,
    memo TEXT,
    updated_by VARCHAR(255),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS manager_pay_rates (
    id SERIAL PRIMARY KEY,
    manager_id INTEGER NOT NULL,
    pay_type VARCHAR(10) NOT NULL CHECK (pay_type IN ('monthly', 'hourly', 'none')),
    amount INTEGER NOT NULL DEFAULT 0 CHECK (amount >= 0),
    effective_from DATE NOT NULL,
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_pay_rates_active
    ON manager_pay_rates (manager_id, effective_from) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS vehicles (
    id SERIAL PRIMARY KEY,
    plate_no VARCHAR(20) NOT NULL,
    model VARCHAR(100),
    fuel_type VARCHAR(10) NOT NULL DEFAULT 'diesel' CHECK (fuel_type IN ('gasoline', 'diesel', 'lpg', 'ev')),
    fuel_efficiency NUMERIC(6, 2),                  -- 공인연비 km/L (EV는 km/kWh)
    purchase_date DATE,
    purchase_price INTEGER CHECK (purchase_price IS NULL OR purchase_price >= 0),
    memo TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by VARCHAR(255),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_vehicles_plate ON vehicles (plate_no) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS vehicle_assignments (
    id SERIAL PRIMARY KEY,
    manager_id INTEGER NOT NULL,
    vehicle_id INTEGER REFERENCES vehicles(id),     -- NULL = 차량 없음
    start_date DATE NOT NULL,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_assign_active
    ON vehicle_assignments (manager_id, start_date) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS vehicle_period_costs (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    category VARCHAR(20) NOT NULL CHECK (category IN ('insurance', 'tax', 'inspection', 'other')),
    amount INTEGER NOT NULL CHECK (amount > 0),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ,
    CHECK (end_date >= start_date)
);
CREATE INDEX IF NOT EXISTS ix_period_costs_range ON vehicle_period_costs (start_date, end_date);

CREATE TABLE IF NOT EXISTS vehicle_expenses (
    id SERIAL PRIMARY KEY,
    vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
    expense_date DATE NOT NULL,
    category VARCHAR(20) NOT NULL
        CHECK (category IN ('repair', 'maintenance', 'tire', 'depreciation', 'parking', 'wash', 'other')),
    amount INTEGER NOT NULL CHECK (amount > 0),
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_expenses_date ON vehicle_expenses (expense_date);
