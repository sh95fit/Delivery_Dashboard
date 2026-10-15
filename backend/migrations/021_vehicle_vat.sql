-- S3-P1b-2a 차량 부가세 공제 여부. 공제 차량은 부가세 붙는 항목을 공급가액으로, 불공제 차량은 합계로 물류비 반영
-- 이 파일에는 콜론과 퍼센트 기호를 쓰지 않는다
ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS vat_deductible BOOLEAN NOT NULL DEFAULT FALSE;
