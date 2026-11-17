-- S2-P4e 동승 (첫 출근 교육 등) - 인건비는 그날 계정으로, 담당·차량 판정에서는 제외
ALTER TABLE work_logs ADD COLUMN IF NOT EXISTS ride_along BOOLEAN NOT NULL DEFAULT FALSE;
