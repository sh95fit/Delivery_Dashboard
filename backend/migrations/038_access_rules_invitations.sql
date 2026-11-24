-- P11-c 접근 규칙(이메일/도메인 → 권한셋) + 초대(해시 토큰) + 시스템 마스터 지정 (멱등)
-- 규칙: 이메일 규칙 > 도메인 규칙. 로그인은 accounts(초대 수락으로만 생성) + 규칙이 모두 있어야 허용.
-- 기존 invitations(0건)·auth_allowlist·accounts.auth_permission_set_id 는 정리 단계에서 제거 예정.

-- 1) 접근 규칙
CREATE TABLE IF NOT EXISTS auth_access_rules (
    id SERIAL PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('email', 'domain')),
    value TEXT NOT NULL,
    permission_set_id INT NOT NULL REFERENCES auth_permission_sets(id),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    memo TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT,
    updated_at TIMESTAMPTZ,
    deleted_by TEXT,
    deleted_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_auth_access_rules_kind_value
    ON auth_access_rules (kind, lower(value)) WHERE deleted_at IS NULL;

-- 2) 초대 (토큰 원문은 저장하지 않음 — SHA-256 해시만 보관)
CREATE TABLE IF NOT EXISTS auth_invitations (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    token_hash TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'accepted', 'revoked')),
    invited_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    sent_at TIMESTAMPTZ,
    send_error TEXT,
    accepted_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_auth_invitations_email
    ON auth_invitations (lower(email));
-- 한 이메일당 대기 중 초대는 1건만 (재발송 시 기존 건 revoke 후 새로 발급)
CREATE UNIQUE INDEX IF NOT EXISTS ux_auth_invitations_pending
    ON auth_invitations (lower(email)) WHERE status = 'pending';

-- 3) 계정 — 초대 수락 기록
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS invitation_id INT REFERENCES auth_invitations(id);
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS activated_at TIMESTAMPTZ;

-- 기존 계정(이미 사용 중인 사용자)은 수락 완료로 간주
UPDATE accounts SET activated_at = created_at
WHERE activated_at IS NULL AND deleted_at IS NULL;

-- 4) 허용목록 → 접근 규칙 이관 (운영 DB에만 있는 테이블 — 없으면 통과)
DO $$
BEGIN
    IF to_regclass('auth_allowlist') IS NOT NULL THEN
        INSERT INTO auth_access_rules (kind, value, permission_set_id, created_by)
        SELECT a.kind,
               lower(a.value),
               COALESCE(
                   (SELECT c.auth_permission_set_id FROM accounts c
                     WHERE a.kind = 'email' AND c.email = lower(a.value)),
                   (SELECT s.id FROM auth_permission_sets s WHERE s.name = '열람')
               ),
               'migration038'
        FROM auth_allowlist a
        WHERE a.kind IN ('email', 'domain')
          AND NOT EXISTS (
              SELECT 1 FROM auth_access_rules r
               WHERE r.kind = a.kind
                 AND lower(r.value) = lower(a.value)
                 AND r.deleted_at IS NULL);
    END IF;
END $$;

-- 5) 시스템 마스터 지정 (마스터를 추가하려면 IN 목록에 이메일 추가)
UPDATE accounts SET is_super = TRUE
WHERE email IN ('shkim@lunchlab.me', 'h95fit@gmail.com') AND is_super = FALSE;
