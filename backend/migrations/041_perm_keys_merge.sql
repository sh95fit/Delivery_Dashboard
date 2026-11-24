-- P11-c 권한키 통합 (멱등): 옛 키 권한을 새 키에 OR로 합친 뒤 옛 키 삭제
-- routes→dashboard(RCUD) · fuel→vehicles(RCUD)
-- worklog_close(C/U)→worklogs.U · worklog_export→worklogs(제거만, 내보내기는 R로 판정)
-- incentive_rates: R→incentive.R, C/U/D→incentive.U
-- 기존에 할 수 있던 기능을 잃지 않도록 OR 병합. 옛 키가 없는 행은 대상 아님(재실행 안전).
UPDATE auth_permission_sets
SET grants = (grants - 'routes' - 'fuel' - 'worklog_close' - 'worklog_export' - 'incentive_rates')
  || jsonb_build_object(
    'dashboard', jsonb_build_object(
      'R', COALESCE((grants->'dashboard'->>'R')::boolean, false) OR COALESCE((grants->'routes'->>'R')::boolean, false),
      'C', COALESCE((grants->'dashboard'->>'C')::boolean, false) OR COALESCE((grants->'routes'->>'C')::boolean, false),
      'U', COALESCE((grants->'dashboard'->>'U')::boolean, false) OR COALESCE((grants->'routes'->>'U')::boolean, false),
      'D', COALESCE((grants->'dashboard'->>'D')::boolean, false) OR COALESCE((grants->'routes'->>'D')::boolean, false)),
    'vehicles', jsonb_build_object(
      'R', COALESCE((grants->'vehicles'->>'R')::boolean, false) OR COALESCE((grants->'fuel'->>'R')::boolean, false),
      'C', COALESCE((grants->'vehicles'->>'C')::boolean, false) OR COALESCE((grants->'fuel'->>'C')::boolean, false),
      'U', COALESCE((grants->'vehicles'->>'U')::boolean, false) OR COALESCE((grants->'fuel'->>'U')::boolean, false),
      'D', COALESCE((grants->'vehicles'->>'D')::boolean, false) OR COALESCE((grants->'fuel'->>'D')::boolean, false)),
    'worklogs', jsonb_build_object(
      'R', COALESCE((grants->'worklogs'->>'R')::boolean, false),
      'C', COALESCE((grants->'worklogs'->>'C')::boolean, false),
      'U', COALESCE((grants->'worklogs'->>'U')::boolean, false)
           OR COALESCE((grants->'worklog_close'->>'C')::boolean, false)
           OR COALESCE((grants->'worklog_close'->>'U')::boolean, false),
      'D', COALESCE((grants->'worklogs'->>'D')::boolean, false)),
    'incentive', jsonb_build_object(
      'R', COALESCE((grants->'incentive'->>'R')::boolean, false) OR COALESCE((grants->'incentive_rates'->>'R')::boolean, false),
      'C', COALESCE((grants->'incentive'->>'C')::boolean, false),
      'U', COALESCE((grants->'incentive'->>'U')::boolean, false)
           OR COALESCE((grants->'incentive_rates'->>'C')::boolean, false)
           OR COALESCE((grants->'incentive_rates'->>'U')::boolean, false)
           OR COALESCE((grants->'incentive_rates'->>'D')::boolean, false),
      'D', COALESCE((grants->'incentive'->>'D')::boolean, false))
  )
WHERE grants->'routes' IS NOT NULL
   OR grants->'fuel' IS NOT NULL
   OR grants->'worklog_close' IS NOT NULL
   OR grants->'worklog_export' IS NOT NULL
   OR grants->'incentive_rates' IS NOT NULL;
