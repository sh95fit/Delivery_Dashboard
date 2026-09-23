CREATE TABLE IF NOT EXISTS route_snapshots (
    id SERIAL PRIMARY KEY,
    snapshot_at TIMESTAMPTZ DEFAULT NOW(),
    route_date DATE NOT NULL,
    manager_id INTEGER NOT NULL,
    state VARCHAR(20) NOT NULL,
    trigger_reason VARCHAR(50) NOT NULL,
    origin_name VARCHAR(255),
    completed_stop_ids_json JSONB DEFAULT '[]'::jsonb,
    remaining_stop_ids_json JSONB DEFAULT '[]'::jsonb,
    completed_path_json JSONB DEFAULT '[]'::jsonb,
    remaining_path_json JSONB DEFAULT '[]'::jsonb,
    distance_m INTEGER DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    toll_fare INTEGER DEFAULT 0,
    fuel_price_naver INTEGER DEFAULT 0,
    fuel_price_opinet INTEGER,
    payload JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_route_snapshots_date_manager
ON route_snapshots (route_date, manager_id, snapshot_at DESC);
