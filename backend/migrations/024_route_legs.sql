-- S3-P2d-2a 실제 경로 구간 (NAVER Directions 5) + NAVER 호출 수 기록
-- 구간 1줄 = 마지막 연결 지점 → 다음 완료 지점. 한 번 저장한 구간은 다시 계산하지 않는다.
CREATE TABLE IF NOT EXISTS route_legs (
    id BIGSERIAL PRIMARY KEY,
    route_date DATE NOT NULL,
    manager_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    from_lat DOUBLE PRECISION NOT NULL,
    from_lng DOUBLE PRECISION NOT NULL,
    to_lat DOUBLE PRECISION NOT NULL,
    to_lng DOUBLE PRECISION NOT NULL,
    to_stop_ids TEXT[] NOT NULL,
    delivered_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'same', 'unreachable')),
    error_code INTEGER,
    distance_m INTEGER NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    fuel_price_naver INTEGER NOT NULL DEFAULT 0,
    toll_fare INTEGER NOT NULL DEFAULT 0,
    ncp_mileage NUMERIC(6,2),
    path JSONB,
    purpose TEXT NOT NULL DEFAULT 'legs',
    calc_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (route_date, manager_id, seq)
);
CREATE INDEX IF NOT EXISTS route_legs_date_idx ON route_legs (route_date);

CREATE TABLE IF NOT EXISTS naver_call_log (
    call_date DATE NOT NULL,
    api TEXT NOT NULL,
    purpose TEXT NOT NULL,
    n INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (call_date, api, purpose)
);
