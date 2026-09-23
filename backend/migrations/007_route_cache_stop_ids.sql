-- 007: route_cache에 stop_ids 컬럼 추가 (v4에서 _cache_get이 SELECT하기 때문)
ALTER TABLE route_cache
    ADD COLUMN IF NOT EXISTS completed_stop_ids_json JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS remaining_stop_ids_json JSONB DEFAULT '[]'::jsonb;