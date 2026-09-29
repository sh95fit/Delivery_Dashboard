-- 008: 경로 엔진 v2 + 그룹 관리 + 비용 파라미터 + 권한
-- 모든 테이블은 멱등(IF NOT EXISTS). CI에서 2회 적용 검증.

-- ========== 1. 경로 엔진 v2 ==========

CREATE TABLE IF NOT EXISTS route_mirror (
    id SERIAL PRIMARY KEY,
    delivery_id VARCHAR(64) NOT NULL,
    route_date DATE NOT NULL,
    address_id BIGINT NOT NULL,
    manager_id INTEGER,
    delivered_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(delivery_id)
);
CREATE INDEX IF NOT EXISTS ix_mirror_date_mgr ON route_mirror (route_date, manager_id);

CREATE TABLE IF NOT EXISTS delivery_events (
    id SERIAL PRIMARY KEY,
    delivery_id VARCHAR(64) NOT NULL,
    route_date DATE NOT NULL,
    address_id BIGINT NOT NULL,
    manager_id INTEGER,
    event_type VARCHAR(20) NOT NULL,
    event_at TIMESTAMPTZ DEFAULT NOW(),
    processed BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS ix_events_date ON delivery_events (route_date, processed);

CREATE TABLE IF NOT EXISTS route_plans (
    id SERIAL PRIMARY KEY,
    route_date DATE NOT NULL,
    group_code VARCHAR(10) NOT NULL,
    manager_id INTEGER,
    stop_sequence INTEGER NOT NULL,
    delivery_id VARCHAR(64) NOT NULL,
    address_id BIGINT NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    eta_minutes INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(route_date, group_code, stop_sequence)
);
CREATE INDEX IF NOT EXISTS ix_plans_date_mgr ON route_plans (route_date, manager_id);

CREATE TABLE IF NOT EXISTS route_segments (
    id SERIAL PRIMARY KEY,
    route_date DATE NOT NULL,
    manager_id INTEGER NOT NULL,
    from_delivery_id VARCHAR(64) NOT NULL,
    to_delivery_id VARCHAR(64) NOT NULL,
    actual_seconds INTEGER NOT NULL,
    naver_seconds INTEGER,
    dwell_seconds INTEGER,
    segment_km NUMERIC(8,2),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_segments_mgr ON route_segments (manager_id, route_date);

CREATE TABLE IF NOT EXISTS route_view_data (
    id SERIAL PRIMARY KEY,
    route_date DATE NOT NULL,
    manager_id INTEGER NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_stops JSONB DEFAULT '[]'::jsonb,
    remaining_stops JSONB DEFAULT '[]'::jsonb,
    completed_path JSONB DEFAULT '[]'::jsonb,
    remaining_path JSONB DEFAULT '[]'::jsonb,
    distance_m INTEGER DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    last_stop_delivery_id VARCHAR(64),
    UNIQUE(route_date, manager_id)
);
CREATE INDEX IF NOT EXISTS ix_view_date ON route_view_data (route_date);

CREATE TABLE IF NOT EXISTS route_job_queue (
    id SERIAL PRIMARY KEY,
    route_date DATE NOT NULL,
    manager_id INTEGER NOT NULL,
    reason VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    requested_by VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS ix_queue_status ON route_job_queue (status, created_at);

CREATE TABLE IF NOT EXISTS api_usage_log (
    id SERIAL PRIMARY KEY,
    usage_date DATE NOT NULL,
    provider VARCHAR(20) NOT NULL DEFAULT 'naver',
    endpoint VARCHAR(60) NOT NULL,
    calls INTEGER NOT NULL DEFAULT 1,
    triggered_by VARCHAR(40) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(usage_date, provider, endpoint, triggered_by)
);

CREATE TABLE IF NOT EXISTS naver_responses (
    id SERIAL PRIMARY KEY,
    route_date DATE NOT NULL,
    manager_id INTEGER,
    request_hash VARCHAR(64) NOT NULL,
    request_body JSONB,
    response_body JSONB,
    http_status INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_naver_date ON naver_responses (route_date);

-- ========== 2. 그룹 관리 ==========

CREATE TABLE IF NOT EXISTS daily_groups (
    id SERIAL PRIMARY KEY,
    group_date DATE NOT NULL,
    group_code VARCHAR(10) NOT NULL,
    trip_sequence INTEGER NOT NULL,
    planned_pack_done_at TIME,
    meal_type VARCHAR(10) NOT NULL DEFAULT 'lunch',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(group_date, meal_type, group_code)
);
CREATE INDEX IF NOT EXISTS ix_groups_date ON daily_groups (group_date, meal_type);

CREATE TABLE IF NOT EXISTS daily_group_managers (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES daily_groups(id) ON DELETE CASCADE,
    manager_id INTEGER NOT NULL,
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(group_id, manager_id)
);
CREATE INDEX IF NOT EXISTS ix_dgm_group ON daily_group_managers (group_id);

CREATE TABLE IF NOT EXISTS group_assignment_history (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL,
    changed_at TIMESTAMPTZ DEFAULT NOW(),
    changed_by VARCHAR(255),
    field_changed VARCHAR(50) NOT NULL,
    old_value TEXT,
    new_value TEXT,
    change_reason TEXT
);

CREATE TABLE IF NOT EXISTS daily_group_meal_counts (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES daily_groups(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL,
    meal_count_auto INTEGER NOT NULL DEFAULT 0,
    meal_count INTEGER,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(group_id, product_id)
);
CREATE INDEX IF NOT EXISTS ix_group_meal_group ON daily_group_meal_counts (group_id);

-- ========== 3. 비용 파라미터 ==========

CREATE TABLE IF NOT EXISTS cost_parameters (
    id SERIAL PRIMARY KEY,
    parameter_name VARCHAR(100) NOT NULL UNIQUE,
    parameter_value NUMERIC(15,4),
    parameter_text TEXT,
    unit VARCHAR(30),
    description TEXT,
    updated_by VARCHAR(255),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO cost_parameters (parameter_name, parameter_value, unit, description) VALUES
    ('dwell_time_seconds',            300,   'seconds', '배송지 머무는 시간 초기값(5분)'),
    ('auto_refresh_interval_min',     30,    'minutes', '운영시간 중 자동 갱신 간격'),
    ('urgent_before_minutes',         30,    'minutes', '희망 배송시간 임박 경고 기준'),
    ('logistics_cost_target_pct',     10.0,  '%',       '물류비 비율 목표치(초과 경고)'),
    ('service_time_per_stop',         180,   'seconds', 'ETA 계산용 정차 시간 추정값'),
    ('default_work_hours',            8.0,   'hours',   '출퇴근 기록 없을 때 기본 근무시간'),
    ('include_return_distance',       1,     'boolean', '1=복귀 거리 포함'),
    ('fuel_efficiency_buffer',        0.9,   'ratio',   '실연비 없을 때 공인연비 배율'),
    ('max_api_calls_per_day',         150,   'count',   'NAVER 일일 상한(방어선)'),
    ('monthly_api_alert_threshold',   2500,  'count',   '월 누적 경고 임계값')
ON CONFLICT (parameter_name) DO NOTHING;

-- ========== 4. 권한 ==========

CREATE TABLE IF NOT EXISTS permission_sets (
    id SERIAL PRIMARY KEY,
    set_name VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO permission_sets (set_name, description) VALUES
    ('admin',    '시스템 어드민 — 전체 권한'),
    ('operator', '운영 관리자 — 기록 입력·운영 화면'),
    ('viewer',   '조회 전용 — 운영·분석 화면 + 시뮬레이터')
ON CONFLICT (set_name) DO NOTHING;

CREATE TABLE IF NOT EXISTS permission_set_pages (
    id SERIAL PRIMARY KEY,
    set_id INTEGER NOT NULL REFERENCES permission_sets(id) ON DELETE CASCADE,
    page_key VARCHAR(60) NOT NULL,
    can_view BOOLEAN NOT NULL DEFAULT FALSE,
    can_edit BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE(set_id, page_key)
);

CREATE TABLE IF NOT EXISTS account_permission_sets (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    set_id INTEGER NOT NULL REFERENCES permission_sets(id),
    is_system_admin BOOLEAN NOT NULL DEFAULT FALSE,
    granted_at TIMESTAMPTZ DEFAULT NOW()
);
