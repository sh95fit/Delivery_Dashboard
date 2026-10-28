from datetime import date

from fastapi import APIRouter, Depends, Query

from app.auth import get_current_email
from app.deps import guard, memo, require_admin
from app.schemas.masters import (EvRateBatchCommitIn, EvRateBatchFileIn, EvRateCommitIn, EvRateFileIn, EvSettingsIn,
                                 FuelCloseIn, FuelImportIn, FuelImportPreviewIn, FuelLogIn, FuelPriceIn, FuelReleaseIn,
                                 FuelUndoIn)
from app.services import fuel_price_service as svc
from app.services import fuel_log_service as logs_svc
from app.services import fuel_export
from app.services import fuel_import_service as import_svc
from app.services import ev_rate_service as ev_svc
from app.services.excel_export import xlsx_response

router = APIRouter(prefix="/fuel", tags=["fuel"])


@router.get("/prices")
def prices(frm: date = Query(..., alias="from"), to: date = Query(...), _: str = Depends(get_current_email)):
    return guard(svc.list_prices, frm, to, fail="유가 조회 실패")


@router.post("/prices")
def add_price(body: FuelPriceIn, email: str = Depends(require_admin)):
    new_id = guard(svc.add_manual, body.price_date, body.fuel_type, body.price, memo(body.memo), email,
                   fail="단가 저장 실패")
    return {"ok": True, "id": new_id}


@router.delete("/prices/{pid}")
def delete_price(pid: int, email: str = Depends(require_admin)):
    guard(svc.delete_manual, pid, email, fail="단가 삭제 실패")
    return {"ok": True}


@router.post("/prices/fetch")
def fetch_now(_: str = Depends(require_admin)):
    return {"ok": True, "saved": guard(svc.fetch_opinet, fail="오피넷 수집 실패")}


@router.get("/prices/daily")
def prices_daily(month: str = Query(...), _: str = Depends(get_current_email)):
    return guard(svc.daily_prices, month, fail="일자별 단가 조회 실패")


@router.post("/prices/fill")
def fill_now(frm: date = Query(..., alias="from"), to: date = Query(...), _: str = Depends(require_admin)):
    return guard(svc.fill_prices, frm, to, fail="오피넷 단가 불러오기 실패")


# ---------- S3-P1b-2b 주유 기록 · 월 집계 · 월 마감 ----------
@router.get("/logs")
def logs(month: str = Query(...), vehicle_id: int | None = Query(default=None),
         _: str = Depends(get_current_email)):
    return guard(logs_svc.list_logs, month, vehicle_id, fail="주유 기록 조회 실패")


@router.post("/logs")
def add_log(body: FuelLogIn, email: str = Depends(require_admin)):
    new_id = guard(logs_svc.add_log, body.model_dump(), email, fail="주유 기록 저장 실패")
    return {"ok": True, "id": new_id}


@router.delete("/logs/{lid}")
def delete_log(lid: int, email: str = Depends(require_admin)):
    guard(logs_svc.delete_log, lid, email, fail="주유 기록 삭제 실패")
    return {"ok": True}


@router.get("/summary")
def summary(month: str = Query(...), _: str = Depends(get_current_email)):
    return guard(logs_svc.month_summary, month, fail="유류비 집계 실패")


@router.post("/closings/{month}")
def close_month(month: str, body: FuelCloseIn, email: str = Depends(require_admin)):
    guard(logs_svc.close_month, month, memo(body.memo), email, fail="유류비 마감 실패")
    return {"ok": True}


@router.post("/closings/{month}/release")
def release_month(month: str, body: FuelReleaseIn, email: str = Depends(require_admin)):
    guard(logs_svc.release_month, month, body.reason, email, fail="유류비 마감 해제 실패")
    return {"ok": True}


# ---------- S3-P1b-2b-3 엑셀 업로드 · 되돌리기 · 내보내기 ----------
@router.post("/import/preview")
def import_preview(body: FuelImportPreviewIn, _: str = Depends(require_admin)):
    return guard(import_svc.preview, body.content_b64, body.file_name, body.vehicle_map, fail="엑셀 미리보기 실패")


@router.post("/import")
def import_commit(body: FuelImportIn, email: str = Depends(require_admin)):
    return guard(import_svc.commit, body.content_b64, body.file_name, body.vehicle_map, body.rows, email,
                 fail="엑셀 저장 실패")


@router.get("/imports")
def imports(month: str = Query(...), _: str = Depends(get_current_email)):
    return guard(import_svc.list_imports, month, fail="업로드 기록 조회 실패")


@router.post("/imports/{iid}/undo")
def import_undo(iid: int, body: FuelUndoIn, email: str = Depends(require_admin)):
    return guard(import_svc.undo_import, iid, body.reason, email, fail="업로드 되돌리기 실패")

@router.get("/export")
def export_month(month: str = Query(...), _: str = Depends(get_current_email)):
    name, sheets = guard(fuel_export.month_sheets, month, fail="유류비 내보내기 실패") 
    return xlsx_response(name, sheets)


# ---------- S3-P2g-1 전기차 충전 단가 (로밍 요금 매트릭스) · 예상 충전비 설정 ----------
@router.get("/ev-rates")
def ev_rates(_: str = Depends(get_current_email)):
    return guard(ev_svc.list_sets, fail="충전 단가 조회 실패")


@router.get("/ev-rates/{sid}/rates")
def ev_rate_detail(sid: int, _: str = Depends(get_current_email)):
    return guard(ev_svc.rates_of, sid, fail="충전 단가 조회 실패")


@router.post("/ev-rates/preview")
def ev_rate_preview(body: EvRateFileIn, _: str = Depends(require_admin)):
    return guard(ev_svc.preview, body.content_b64, body.file_name, fail="요금 매트릭스 미리보기 실패")


@router.post("/ev-rates/settings")
def ev_settings(body: EvSettingsIn, email: str = Depends(require_admin)):
    return guard(ev_svc.save_settings, body.ev_speed, body.ev_km_per_kwh, email, fail="충전비 설정 저장 실패")


@router.post("/ev-rates")
def ev_rate_commit(body: EvRateCommitIn, email: str = Depends(require_admin)):
    return guard(ev_svc.commit, body.content_b64, body.file_name, body.speed, body.effective_from,
                 memo(body.memo), email, fail="충전 단가 저장 실패")


# ---------- S3-P2g-1d 여러 파일 한 번에 (최대 5개) ----------
@router.post("/ev-rates/batch/preview")
def ev_rate_batch_preview(body: EvRateBatchFileIn, _: str = Depends(require_admin)):
    return guard(ev_svc.preview_batch, [f.model_dump() for f in body.files], fail="요금 매트릭스 미리보기 실패")


@router.post("/ev-rates/batch")
def ev_rate_batch_commit(body: EvRateBatchCommitIn, email: str = Depends(require_admin)):
    items = [{**i.model_dump(), "memo": memo(i.memo)} for i in body.items]
    return guard(ev_svc.commit_batch, items, email, fail="충전 단가 저장 실패")


@router.delete("/ev-rates/{sid}")
def ev_rate_delete(sid: int, email: str = Depends(require_admin)):
    guard(ev_svc.delete_set, sid, email, fail="충전 단가 삭제 실패")
    return {"ok": True}

