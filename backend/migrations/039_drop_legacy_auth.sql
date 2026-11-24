-- P11-c 레거시 정리 (멱등): 허용목록·구 초대·계정 직결 권한셋 제거
-- 038에서 auth_access_rules로 이관 완료. 신규 코드는 아래 객체를 참조하지 않음.
DROP TABLE IF EXISTS auth_allowlist;
DROP TABLE IF EXISTS invitations;
ALTER TABLE accounts DROP COLUMN IF EXISTS auth_permission_set_id;
