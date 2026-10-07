from fastapi import APIRouter, Depends

from app.auth import get_current_email
from app.deps import guard, memo, require_admin
from app.schemas.workers import ImportCommitIn, ImportExcelIn, WorkerAccountIn, WorkerIn, WorkerRateIn
from app.services import dash_db, worker_import
from app.services import worker_service as svc

router = APIRouter(prefix="/workers", tags=["workers"])


@router.get("")
def list_workers(_: str = Depends(get_current_email)):
    return {"items": guard(svc.list_workers, fail="인력 조회 실패")}


@router.post("/import/excel")
def import_excel_preview(body: ImportExcelIn, _: str = Depends(require_admin)):
    return guard(worker_import.preview_excel, body.content_b64, body.file_income, fail="근무표 읽기 실패")


@router.get("/import/accounts")
def import_account_candidates(_: str = Depends(require_admin)):
    return {"items": guard(worker_import.account_candidates, fail="운영 계정 조회 실패")}


@router.post("/import/commit")
def import_commit(body: ImportCommitIn, email: str = Depends(require_admin)):
    rows = [r.model_dump() for r in body.rows]
    for r in rows:
        r["memo"] = memo(r.get("memo"))
    return guard(worker_import.commit, rows, email, fail="일괄 등록 실패")


@router.get("/{wid}")
def worker_detail(wid: int, _: str = Depends(get_current_email)):
    return guard(svc.worker_detail, wid, fail="인력 상세 조회 실패")


@router.post("")
def create_worker(body: WorkerIn, email: str = Depends(require_admin)):
    new_id = guard(svc.save_worker, None, body.name, body.income_type, body.active, memo(body.memo), email,
                   fail="인력 등록 실패")
    return {"ok": True, "id": new_id}


@router.put("/{wid}")
def update_worker(wid: int, body: WorkerIn, email: str = Depends(require_admin)):
    guard(svc.save_worker, wid, body.name, body.income_type, body.active, memo(body.memo), email,
          fail="인력 저장 실패")
    return {"ok": True, "id": wid}


@router.post("/{wid}/rates")
def add_rate(wid: int, body: WorkerRateIn, email: str = Depends(require_admin)):
    data = body.model_dump()
    data["memo"] = memo(body.memo)
    return {"ok": True, "id": guard(svc.add_rate, wid, data, email, fail="계약 조건 저장 실패")}


@router.put("/rates/{rid}")
def update_rate(rid: int, body: WorkerRateIn, email: str = Depends(require_admin)):
    data = body.model_dump()
    data["memo"] = memo(body.memo)
    return {"ok": True, "id": guard(svc.update_rate, rid, data, email, fail="계약 조건 수정 실패")}


@router.delete("/rates/{rid}")
def delete_rate(rid: int, email: str = Depends(require_admin)):
    guard(dash_db.soft_delete, "worker_pay_rates", rid, email, fail="삭제 실패")
    return {"ok": True}


@router.post("/{wid}/accounts")
def assign_account(wid: int, body: WorkerAccountIn, email: str = Depends(require_admin)):
    new_id = guard(svc.assign_account, wid, body.manager_id, body.start_date, email, fail="계정 배정 실패")
    return {"ok": True, "id": new_id}


@router.put("/accounts/{aid}")
def update_account(aid: int, body: WorkerAccountIn, email: str = Depends(require_admin)):
    new_id = guard(svc.update_account, aid, body.manager_id, body.start_date, email, fail="계정 이력 수정 실패")
    return {"ok": True, "id": new_id}


@router.delete("/accounts/{aid}")
def delete_account(aid: int, email: str = Depends(require_admin)):
    guard(dash_db.soft_delete, "worker_accounts", aid, email, fail="삭제 실패")
    return {"ok": True}
