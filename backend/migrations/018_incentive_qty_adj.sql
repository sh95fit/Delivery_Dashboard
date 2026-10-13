-- S2-P4c-1c 제품 수 조정 목록(라인업별 또는 제품 총량), 특수 수당 같은 품목 여러 줄 허용
-- 이 파일에는 콜론과 퍼센트 기호를 쓰지 않는다 (마이그레이션 실행기가 text() 사용)

CREATE TABLE IF NOT EXISTS incentive_qty_adjustments (
    id SERIAL PRIMARY KEY,
    manager_id INTEGER NOT NULL,
    work_date DATE NOT NULL,
    product_id INTEGER,
    qty INTEGER NOT NULL CHECK (qty <> 0 AND qty BETWEEN -2000 AND 2000),
    reason TEXT NOT NULL,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_by VARCHAR(255),
    deleted_at TIMESTAMPTZ,
    delete_reason TEXT
);
-- product_id 가 NULL 이면 제품 총량 조정, 값이 있으면 그 라인업(4, 23, 29) 조정
CREATE INDEX IF NOT EXISTS ix_inc_qty_adj
    ON incentive_qty_adjustments (work_date, manager_id) WHERE deleted_at IS NULL;

-- 기존 한 줄짜리 조정을 제품 총량 조정 목록으로 옮기고 옛 행은 삭제 표시
INSERT INTO incentive_qty_adjustments (manager_id, work_date, product_id, qty, reason, created_by, created_at)
SELECT a.manager_id, a.adj_date, NULL, a.value,
       COALESCE(NULLIF(TRIM(a.reason), ''), '이전 조정 이관'), a.created_by, a.created_at
FROM incentive_adjustments a
WHERE a.field = 'product_delta' AND a.deleted_at IS NULL AND a.value <> 0;

UPDATE incentive_adjustments SET deleted_at = NOW(), deleted_by = 'migration-018'
WHERE field = 'product_delta' AND deleted_at IS NULL;

-- 특수 수당 = 같은 날 같은 품목 여러 줄 허용 (중복 여부는 화면 경고로 확인)
DROP INDEX IF EXISTS ux_inc_extras;
CREATE INDEX IF NOT EXISTS ix_inc_extras_mgr_date
    ON incentive_extras (work_date, manager_id) WHERE deleted_at IS NULL;
