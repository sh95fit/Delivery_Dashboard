-- P11-b 계정 부트스트랩 (멱등)
-- 허용 목록(auth_allowlist)의 이메일 계정을 '열람'으로 자동 생성.
-- auth_allowlist는 마이그레이션으로 만드는 테이블이 아니라 운영 DB에만 있으므로,
-- DO 블록에서 테이블 존재 확인 후 실행 — 없는 환경(CI 등)은 아무 것도 하지 않고 통과.
-- (계정이 안 만들어져도 기능에는 지장 없음 — 로그인 시점에 '열람' 자동 계정이 실제 경로)
DO $$
BEGIN
    IF to_regclass('auth_allowlist') IS NOT NULL THEN
        INSERT INTO accounts (email, auth_permission_set_id, active, created_by)
        SELECT a.value,
               (SELECT id FROM auth_permission_sets WHERE name = '열람'),
               TRUE, 'migration037'
        FROM auth_allowlist a
        WHERE a.kind = 'email'
          AND NOT EXISTS (SELECT 1 FROM accounts x WHERE x.email = lower(a.value));
    END IF;
END $$;
