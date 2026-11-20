-- P11-a 권한셋·계정·초대 기반 (14개 페이지키, 멱등 — CI가 마이그레이션을 2회 실행해도 안전)
-- 이 파일에는 콜론과 퍼센트 기호를 쓰지 않는다 (마이그레이션 실행기가 text() 사용)

CREATE TABLE IF NOT EXISTS permission_sets (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    grants JSONB NOT NULL,
    builtin BOOLEAN NOT NULL DEFAULT FALSE,
    memo TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by TEXT,
    deleted_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    permission_set_id INT REFERENCES permission_sets(id),
    is_super BOOLEAN NOT NULL DEFAULT FALSE,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by TEXT,
    deleted_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_accounts_active ON accounts (active) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS invitations (
    id SERIAL PRIMARY KEY,
    token TEXT UNIQUE NOT NULL,
    email TEXT NOT NULL,
    permission_set_id INT NOT NULL REFERENCES permission_sets(id),
    invited_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);

INSERT INTO permission_sets (name, grants, builtin, memo, created_by)
SELECT '관리자', jsonb_build_object(
  'dashboard', jsonb_build_object('R',true,'C',true,'U',true,'D',true),
  'routes', jsonb_build_object('R',true,'C',true,'U',true,'D',true),
  'worklogs', jsonb_build_object('R',true,'C',true,'U',true,'D',true),
  'worklog_close', jsonb_build_object('R',true,'C',true,'U',true,'D',true),
  'worklog_export', jsonb_build_object('R',true,'C',true,'U',true,'D',true),
  'incentive', jsonb_build_object('R',true,'C',true,'U',true,'D',true),
  'incentive_rates', jsonb_build_object('R',true,'C',true,'U',true,'D',true),
  'logistics', jsonb_build_object('R',true,'C',true,'U',true,'D',true),
  'vehicles', jsonb_build_object('R',true,'C',true,'U',true,'D',true),
  'fuel', jsonb_build_object('R',true,'C',true,'U',true,'D',true),
  'workers', jsonb_build_object('R',true,'C',true,'U',true,'D',true),
  'managers', jsonb_build_object('R',true,'C',true,'U',true,'D',true),
  'internal', jsonb_build_object('R',true,'C',true,'U',true,'D',true),
  'settings', jsonb_build_object('R',true,'C',true,'U',true,'D',true)
), TRUE, '전체 권한', 'migration'
WHERE NOT EXISTS (SELECT 1 FROM permission_sets WHERE name = '관리자');

INSERT INTO permission_sets (name, grants, builtin, memo, created_by)
SELECT '열람', jsonb_build_object(
  'dashboard', jsonb_build_object('R',true),
  'routes', jsonb_build_object('R',true),
  'worklogs', jsonb_build_object('R',true),
  'worklog_close', jsonb_build_object('R',true),
  'worklog_export', jsonb_build_object('R',false),
  'incentive', jsonb_build_object('R',true),
  'incentive_rates', jsonb_build_object('R',false),
  'logistics', jsonb_build_object('R',true),
  'vehicles', jsonb_build_object('R',true),
  'fuel', jsonb_build_object('R',false),
  'workers', jsonb_build_object('R',false),
  'managers', jsonb_build_object('R',false),
  'internal', jsonb_build_object('R',false),
  'settings', jsonb_build_object('R',false)
), TRUE, '읽기 전용 (민감 영역 제외)', 'migration'
WHERE NOT EXISTS (SELECT 1 FROM permission_sets WHERE name = '열람');

INSERT INTO permission_sets (name, grants, builtin, memo, created_by)
SELECT '근태 입력', jsonb_build_object(
  'dashboard', jsonb_build_object('R',true),
  'routes', jsonb_build_object('R',true),
  'worklogs', jsonb_build_object('R',true,'C',true,'U',true),
  'worklog_close', jsonb_build_object('R',true),
  'worklog_export', jsonb_build_object('R',false),
  'incentive', jsonb_build_object('R',true,'C',true,'U',true),
  'incentive_rates', jsonb_build_object('R',false),
  'logistics', jsonb_build_object('R',true),
  'vehicles', jsonb_build_object('R',false),
  'fuel', jsonb_build_object('R',false),
  'workers', jsonb_build_object('R',false),
  'managers', jsonb_build_object('R',false),
  'internal', jsonb_build_object('R',false),
  'settings', jsonb_build_object('R',false)
), TRUE, '근무·인센티브 입력자', 'migration'
WHERE NOT EXISTS (SELECT 1 FROM permission_sets WHERE name = '근태 입력');
