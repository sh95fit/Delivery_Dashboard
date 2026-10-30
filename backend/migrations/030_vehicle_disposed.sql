-- S3-P2h-3b-2 차량 처분일 (판매·폐차). 이 날 뒤로는 차량 이용 이력·그날 예외에 쓸 수 없음
ALTER TABLE vehicles ADD COLUMN IF NOT EXISTS disposed_on DATE;
