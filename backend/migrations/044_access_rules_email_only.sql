-- P11 Step3-5 접근 규칙 = 이메일 전용 (멱등).
-- 043에서 도메인 규칙은 이메일 규칙으로 이전 후 소프트 삭제됨. 여기서는 잔여분 정리 + 재발 방지 제약.

-- 1) 043 이후 남은 활성 도메인 규칙이 있다면 043과 같은 방식으로 이전 → 소프트 삭제
INSERT INTO auth_access_rules (kind, value, permission_set_id, active, created_by)
SELECT DISTINCT ON (a.email) 'email', a.email, r.permission_set_id, TRUE, 'migration044'
FROM accounts a
JOIN auth_access_rules r
  ON r.kind = 'domain' AND r.active AND r.deleted_at IS NULL
 AND lower(r.value) = split_part(a.email, '@', 2)
WHERE a.deleted_at IS NULL
  AND NOT EXISTS (SELECT 1 FROM auth_access_rules x
                   WHERE x.kind = 'email' AND lower(x.value) = a.email AND x.deleted_at IS NULL)
ORDER BY a.email, r.id;

UPDATE auth_access_rules SET active = FALSE, deleted_at = now(), deleted_by = 'migration044'
WHERE kind = 'domain' AND deleted_at IS NULL;

-- 2) 살아있는 규칙은 email만 허용 (소프트 삭제된 도메인 행은 이력으로 보존)
--    038의 기존 CHECK(kind IN ('email','domain'))는 그대로 둔다 (이름 추정 불필요)
ALTER TABLE auth_access_rules DROP CONSTRAINT IF EXISTS ck_auth_access_rules_email_only;
ALTER TABLE auth_access_rules ADD CONSTRAINT ck_auth_access_rules_email_only
    CHECK (kind = 'email' OR deleted_at IS NOT NULL);

-- 3) 활성 이메일 규칙 중복 방지: 038의 ux_auth_access_rules_kind_value
--    (kind, lower(value)) WHERE deleted_at IS NULL 이 이미 보장 → 추가 인덱스 없음
