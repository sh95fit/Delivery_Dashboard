-- 1) 도메인 규칙으로만 접근하던 기존 계정 → 같은 권한셋의 이메일 규칙으로 이전
INSERT INTO auth_access_rules (kind, value, permission_set_id, active)
SELECT DISTINCT ON (a.email) 'email', a.email, r.permission_set_id, TRUE
FROM accounts a
JOIN auth_access_rules r
  ON r.kind = 'domain' AND r.active AND r.deleted_at IS NULL
 AND lower(r.value) = split_part(a.email, '@', 2)
WHERE a.deleted_at IS NULL
  AND NOT EXISTS (SELECT 1 FROM auth_access_rules x
                   WHERE x.kind = 'email' AND lower(x.value) = a.email AND x.deleted_at IS NULL)
ORDER BY a.email, r.id;

-- 2) 도메인 규칙 소프트 삭제 (이력 보존)
UPDATE auth_access_rules SET active = FALSE, deleted_at = now()
WHERE kind = 'domain' AND deleted_at IS NULL;
