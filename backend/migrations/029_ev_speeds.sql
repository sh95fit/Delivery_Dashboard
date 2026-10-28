-- S3-P2g-1c 전기차 충전 속도 5단계 (로밍 요금 매트릭스 파일 구분과 같게)
-- slow 완속 30kW 미만 / mid 중속 30~49kW / fast50 급속 50~99kW / fast100 급속 100~199kW / ultra 초급속 200kW 이상
-- 이 파일에는 콜론과 퍼센트 기호를 쓰지 않는다 (마이그레이션 실행기가 text() 사용). 두 번 실행해도 같은 결과

ALTER TABLE ev_rate_sets DROP CONSTRAINT IF EXISTS ev_rate_sets_speed_check;
UPDATE ev_rate_sets SET speed = 'fast50' WHERE speed = 'fast';
ALTER TABLE ev_rate_sets ADD CONSTRAINT ev_rate_sets_speed_check
    CHECK (speed IN ('slow', 'mid', 'fast50', 'fast100', 'ultra'));

UPDATE cost_settings SET value = 'fast50', updated_at = NOW() WHERE key = 'ev_speed' AND value = 'fast';
