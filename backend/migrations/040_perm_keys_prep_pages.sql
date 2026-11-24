-- P11-c 준비중 화면키 추가 (기존 키 유지 — 추가만, 멱등)
-- packing(포장 그룹) · sales(매출 관리) · analysis(매출·비용 분석) · simulation(시뮬레이션)
-- '관리자' 권한셋은 전체 허용, 그 외는 전체 차단. 이미 키가 있으면 유지(COALESCE).
UPDATE auth_permission_sets
SET grants = grants || jsonb_build_object(
    'packing',    COALESCE(grants->'packing',
                  jsonb_build_object('R', name = '관리자', 'C', name = '관리자', 'U', name = '관리자', 'D', name = '관리자')),
    'sales',      COALESCE(grants->'sales',
                  jsonb_build_object('R', name = '관리자', 'C', name = '관리자', 'U', name = '관리자', 'D', name = '관리자')),
    'analysis',   COALESCE(grants->'analysis',
                  jsonb_build_object('R', name = '관리자', 'C', name = '관리자', 'U', name = '관리자', 'D', name = '관리자')),
    'simulation', COALESCE(grants->'simulation',
                  jsonb_build_object('R', name = '관리자', 'C', name = '관리자', 'U', name = '관리자', 'D', name = '관리자'))
)
WHERE deleted_at IS NULL;
