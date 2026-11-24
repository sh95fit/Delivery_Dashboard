-- P11 Step3-3 초대 = 마스터가 이메일 사전 등록, 수락 = 그 이메일로 첫 구글 로그인 (멱등)
-- 토큰 링크를 쓰지 않으므로 token_hash를 선택 칸으로 바꿈. 만료(expired)는 저장하지 않고 expires_at으로 계산.
ALTER TABLE auth_invitations ALTER COLUMN token_hash DROP NOT NULL;
ALTER TABLE auth_invitations ADD COLUMN IF NOT EXISTS memo TEXT;
ALTER TABLE auth_invitations ADD COLUMN IF NOT EXISTS revoked_by TEXT;
ALTER TABLE auth_invitations ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ;
