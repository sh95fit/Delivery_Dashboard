-- P11-b 계정 부트스트랩 (멱등)
-- 1) ADMIN_EMAILS 이관 대신: 앱 기동 폴백(ADMIN_EMAILS 상시 유효)이 유지되므로 여기선 시드만
--    기존 허용 목록의 이메일 계정을 '열람'으로 자동 생성 (is_super는 앱 기동 시 환경변수 폴백이 흡수)
INSERT INTO accounts (email, auth_permission_set_id, active, created_by)
SELECT a.value,
       (SELECT id FROM auth_permission_sets WHERE name = '열람'),
       TRUE, 'migration037'
FROM auth_allowlist a
WHERE a.kind = 'email'
  AND NOT EXISTS (SELECT 1 FROM accounts x WHERE x.email = lower(a.value));
