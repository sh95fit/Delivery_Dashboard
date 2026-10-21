-- S3-P2d-5 관제 제외 배송지: 지도·집계·실제 경로에는 그대로, 노선 관제(지연 예상·정체·예상 완료·남은 경로)에서만 뺀다
-- 예: 오후에 따로 가는 곳. 모든 날짜에 적용
CREATE TABLE IF NOT EXISTS control_excludes (
    id BIGSERIAL PRIMARY KEY,
    address_id INTEGER NOT NULL,
    label TEXT,
    memo TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by TEXT,
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS control_excludes_active_uq ON control_excludes (address_id) WHERE deleted_at IS NULL;
