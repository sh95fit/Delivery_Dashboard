-- S3-P2g-1 전기차 충전 단가 (로밍 요금 매트릭스) · 비용 설정
-- 이 파일에는 콜론과 퍼센트 기호를 쓰지 않는다 (마이그레이션 실행기가 text() 사용)

-- 1) 요금 매트릭스 묶음. 파일 1개 = 속도 1개 · 적용 시작일 1개. 기준 단가 = 환경부 카드로 환경부 충전기를 쓸 때
CREATE TABLE IF NOT EXISTS ev_rate_sets (
    id              BIGSERIAL PRIMARY KEY,
    speed           VARCHAR(10) NOT NULL CHECK (speed IN ('slow', 'fast', 'ultra')),
    effective_from  DATE NOT NULL,
    issuer          VARCHAR(100) NOT NULL,
    base_price      NUMERIC(8,2) NOT NULL CHECK (base_price > 0),
    rate_count      INTEGER NOT NULL DEFAULT 0,
    file_name       VARCHAR(200),
    file_hash       CHAR(64),
    memo            VARCHAR(200),
    created_by      VARCHAR(200),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by      VARCHAR(200),
    deleted_at      TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_ev_rate_sets_day ON ev_rate_sets (speed, effective_from) WHERE deleted_at IS NULL;

-- 2) 환경부 카드 행의 충전 사업자별 단가 (원/kWh)
CREATE TABLE IF NOT EXISTS ev_rates (
    id        BIGSERIAL PRIMARY KEY,
    set_id    BIGINT NOT NULL REFERENCES ev_rate_sets(id),
    operator  VARCHAR(100) NOT NULL,
    price     NUMERIC(8,2) NOT NULL CHECK (price > 0),
    UNIQUE (set_id, operator)
);

-- 3) 비용 계산 설정 (예상 충전 속도 · 기본 전비)
CREATE TABLE IF NOT EXISTS cost_settings (
    key         VARCHAR(50) PRIMARY KEY,
    value       VARCHAR(200) NOT NULL,
    updated_by  VARCHAR(200),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO cost_settings (key, value) VALUES ('ev_speed', 'fast'), ('ev_km_per_kwh', '3.1')
ON CONFLICT (key) DO NOTHING;
