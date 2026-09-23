CREATE TABLE IF NOT EXISTS route_job_state (
    id SERIAL PRIMARY KEY,
    route_date DATE NOT NULL,
    manager_id INTEGER NOT NULL,
    state VARCHAR(20) NOT NULL,
    current_signature VARCHAR(255) NOT NULL,
    current_route_key VARCHAR(255),
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    next_retry_at TIMESTAMPTZ,
    last_error TEXT,
    last_error_payload JSONB DEFAULT '{}'::jsonb,
    last_changed_at TIMESTAMPTZ DEFAULT NOW(),
    last_collected_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(route_date, manager_id, state)
);
