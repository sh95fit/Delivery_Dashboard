-- P11 Step3-5 초대 메일 발송 이력 (멱등) — 발송 제한(1분 1회·1시간 5회) + 감사 기록
CREATE TABLE IF NOT EXISTS auth_invite_sends (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    invitation_id INT REFERENCES auth_invitations(id),
    kind TEXT NOT NULL CHECK (kind IN ('initial', 'resend')),
    status TEXT NOT NULL DEFAULT 'sending' CHECK (status IN ('sending', 'sent', 'failed')),
    error TEXT,
    requested_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_auth_invite_sends_email_time
    ON auth_invite_sends (lower(email), created_at DESC);
    