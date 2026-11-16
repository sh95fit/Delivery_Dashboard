-- S2-P4d-1b 조기 출근 인정. 기본은 지정 출근보다 이른 지문 = 지정 시각 인정. 체크한 날만 지문 시각 그대로 인정 (한시적 출근 시각 조정)
-- 이 파일에는 콜론과 퍼센트 기호를 쓰지 않는다 (마이그레이션 실행기가 text() 사용)
ALTER TABLE work_logs ADD COLUMN IF NOT EXISTS early_ok BOOLEAN NOT NULL DEFAULT FALSE;
