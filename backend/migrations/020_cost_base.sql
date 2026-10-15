-- S3-P1b-1 물류비 기초 데이터 (유가 기록, 영업일 예외, 비용 항목 추가)
-- 이 파일에는 콜론과 퍼센트 기호를 쓰지 않는다 (마이그레이션 실행기가 text() 사용)

-- 1) 유가 기록. 오피넷 자동 수집(휘발유 경유 LPG) + 직접 입력(전기 충전 단가 등)
--    단위는 원/L, 전기는 원/kWh. 그날 이전 가장 최근 값을 그날 단가로 사용
CREATE TABLE IF NOT EXISTS fuel_price_log (
    id SERIAL PRIMARY KEY,
    price_date DATE NOT NULL,
    fuel_type VARCHAR(10) NOT NULL,
    price NUMERIC(8, 2) NOT NULL
);
ALTER TABLE fuel_price_log
    ADD COLUMN IF NOT EXISTS source VARCHAR(10) NOT NULL DEFAULT 'opinet',
    ADD COLUMN IF NOT EXISTS memo TEXT,
    ADD COLUMN IF NOT EXISTS created_by VARCHAR(255),
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS deleted_by VARCHAR(255),
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
CREATE UNIQUE INDEX IF NOT EXISTS ux_fuel_price_day
    ON fuel_price_log (price_date, fuel_type, source) WHERE deleted_at IS NULL;

-- 2) 영업일 예외. 규칙(월~토 영업, 일요일 공휴일 휴무, 대체공휴일 영업)과 다른 날만 기록
CREATE TABLE IF NOT EXISTS business_day_overrides (
    id SERIAL PRIMARY KEY,
    work_date DATE NOT NULL,
    is_open BOOLEAN NOT NULL,
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_bday_override
    ON business_day_overrides (work_date) WHERE deleted_at IS NULL;

-- 3) 지출 내역 항목 추가 (견인, 사고 처리)
ALTER TABLE vehicle_expenses DROP CONSTRAINT IF EXISTS vehicle_expenses_category_check;
ALTER TABLE vehicle_expenses ADD CONSTRAINT vehicle_expenses_category_check
    CHECK (category IN ('repair', 'maintenance', 'tire', 'towing', 'accident',
                        'depreciation', 'parking', 'wash', 'other'));

-- 4) 기간 비용 항목 추가 (리스 렌트)
ALTER TABLE vehicle_period_costs DROP CONSTRAINT IF EXISTS vehicle_period_costs_category_check;
ALTER TABLE vehicle_period_costs ADD CONSTRAINT vehicle_period_costs_category_check
    CHECK (category IN ('insurance', 'tax', 'inspection', 'lease', 'other'));
