# dash DB 마이그레이션
- 파일명: NNN_설명.sql (번호 절대 중복 금지, 적용된 파일은 절대 수정 금지)
- 스키마 변경이 필요하면: 새 번호 파일 추가 → 커밋·푸시 → 배포 시 자동 적용
- 적용 이력 확인 (서버):
  docker compose exec db psql -U dash_user -d delivery_dashboard -c "SELECT * FROM schema_migrations;"
- 수동 즉시 적용이 필요할 때: docker compose exec backend python -m app.db_migrate
