-- S3-P2h 인력 차량 이용 이력 + 그날 예외. 계정 차량은 날짜별 계정 담당 인력(assign_owner)의 차량으로 정한다
-- 계정 담당 판정은 기존 그대로 (담당 지정 다음 근무 기록 그날 계정 다음 고정 계정)
-- 이 파일에는 콜론과 퍼센트 기호를 쓰지 않는다 (마이그레이션 실행기가 text() 사용)

CREATE TABLE IF NOT EXISTS worker_vehicles (
    id SERIAL PRIMARY KEY,
    worker_id INTEGER NOT NULL REFERENCES workers(id),
    start_date DATE NOT NULL,
    mode VARCHAR(10) NOT NULL CHECK (mode IN ('company', 'own', 'none')),
    vehicle_id INTEGER REFERENCES vehicles(id),
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ,
    CHECK ((mode = 'company') = (vehicle_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_worker_vehicles_active
    ON worker_vehicles (worker_id, start_date) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_worker_vehicles_vehicle
    ON worker_vehicles (vehicle_id) WHERE deleted_at IS NULL;

-- 그날만 다른 차량 (vehicle_id 비움 = 그날 회사 차량 없음)
CREATE TABLE IF NOT EXISTS worker_vehicle_days (
    id SERIAL PRIMARY KEY,
    work_date DATE NOT NULL,
    worker_id INTEGER NOT NULL REFERENCES workers(id),
    vehicle_id INTEGER REFERENCES vehicles(id),
    reason VARCHAR(10) NOT NULL DEFAULT 'other' CHECK (reason IN ('breakdown', 'swap', 'other')),
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_worker_vehicle_days_active
    ON worker_vehicle_days (work_date, worker_id) WHERE deleted_at IS NULL;
