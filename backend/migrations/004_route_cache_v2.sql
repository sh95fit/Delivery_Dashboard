ALTER TABLE route_cache
    ADD COLUMN IF NOT EXISTS state VARCHAR(20),
    ADD COLUMN IF NOT EXISTS completed_path_json JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS remaining_path_json JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS completed_stops INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS remaining_stops INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS toll_fare INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS fuel_price_naver INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS fuel_price_opinet INTEGER,
    ADD COLUMN IF NOT EXISTS origin_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS stop_signature VARCHAR(255),
    ADD COLUMN IF NOT EXISTS payload JSONB DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS ix_route_cache_state ON route_cache (state);
