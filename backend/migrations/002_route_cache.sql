-- 노선 캐시 (Routes API 결과 재사용 — 비용 통제 핵심)
CREATE TABLE IF NOT EXISTS route_cache (
    id SERIAL PRIMARY KEY,
    route_key VARCHAR(120) NOT NULL,        -- 'manager_id:YYYY-MM-DD' (해시 아님 — 사람이 읽게)
    polyline TEXT NOT NULL,
    distance_m INTEGER NOT NULL,
    duration_s INTEGER NOT NULL,
    stops_count INTEGER NOT NULL,
    source VARCHAR(10) NOT NULL DEFAULT 'routes_api',   -- routes_api | fallback_straight
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(route_key)
);

CREATE INDEX IF NOT EXISTS ix_route_cache_key ON route_cache (route_key);
