-- S2-P4b-2 월 마감: 해제 사유, 마감 시점 합계 (중복 실행 안전)
ALTER TABLE month_closings ADD COLUMN IF NOT EXISTS reopen_reason TEXT;
ALTER TABLE month_closings ADD COLUMN IF NOT EXISTS summary JSONB;
