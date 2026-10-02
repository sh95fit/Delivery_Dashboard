-- S1-P1.2 시급제 근무 기준 (예상 물류비용). 실제 출퇴근은 근무일지 단계에서 별도 기록
ALTER TABLE manager_pay_rates ADD COLUMN IF NOT EXISTS work_start TIME;
ALTER TABLE manager_pay_rates ADD COLUMN IF NOT EXISTS work_end TIME;
ALTER TABLE manager_pay_rates ADD COLUMN IF NOT EXISTS break_min INTEGER NOT NULL DEFAULT 0 CHECK (break_min >= 0);
ALTER TABLE manager_pay_rates ADD COLUMN IF NOT EXISTS break_paid BOOLEAN NOT NULL DEFAULT FALSE;
