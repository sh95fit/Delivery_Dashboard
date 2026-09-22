CREATE TABLE IF NOT EXISTS route_origins (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 활성 출발지는 1개만 허용
CREATE UNIQUE INDEX IF NOT EXISTS ux_route_origins_single_active
ON route_origins (is_active)
WHERE is_active = TRUE; 