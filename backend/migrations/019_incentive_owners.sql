-- S2-P4c-2b 계정 그날 담당자 지정 (정규직 포함). 인센티브 배정 1순위
-- 이 파일에는 콜론과 퍼센트 기호를 쓰지 않는다 (마이그레이션 실행기가 text() 사용)

CREATE TABLE IF NOT EXISTS incentive_owners (
    id SERIAL PRIMARY KEY,
    work_date DATE NOT NULL,
    manager_id INTEGER NOT NULL,
    worker_id INTEGER NOT NULL REFERENCES workers(id),
    memo TEXT,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ
);
-- 계정 하나는 하루 담당 한 명. 한 사람이 두 계정을 맡는 것은 허용
CREATE UNIQUE INDEX IF NOT EXISTS ux_inc_owner_acc
    ON incentive_owners (work_date, manager_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_inc_owner_worker
    ON incentive_owners (work_date, worker_id) WHERE deleted_at IS NULL;
