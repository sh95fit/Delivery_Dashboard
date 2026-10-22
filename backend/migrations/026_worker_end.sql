-- S2-P0c 퇴사일 · 정규직 마지막 달 급여 (물류비 인건비: 퇴사일까지 이력 유지)
ALTER TABLE workers ADD COLUMN IF NOT EXISTS end_date DATE;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS last_pay_full BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE workers ADD COLUMN IF NOT EXISTS last_pay_amount INTEGER CHECK (last_pay_amount IS NULL OR last_pay_amount >= 0);