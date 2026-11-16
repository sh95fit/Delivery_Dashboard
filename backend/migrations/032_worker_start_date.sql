-- S2-P4d-1 입사일. 비우면 제한 없음 (계약 시작일 기준 그대로). 입사일 전 = 근무 대상 아님 (미입력 검사 제외, 근무 입력은 허용)
-- 이 파일에는 콜론과 퍼센트 기호를 쓰지 않는다 (마이그레이션 실행기가 text() 사용)
ALTER TABLE workers ADD COLUMN IF NOT EXISTS start_date DATE;
