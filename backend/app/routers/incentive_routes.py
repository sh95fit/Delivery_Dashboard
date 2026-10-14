from datetime import date

from fastapi import APIRouter, Depends, Query

from app.auth import get_current_email
from app.deps import guard, memo, require_admin
from app.schemas.incentive import (AccountsIn, ExclusionIn, ExtraIn, ExtraItemIn, ExtraUpdateIn,
                                   HoldIn, QtyAdjIn, RateSetIn, ReasonIn, OwnerIn)
from app.services import incentive_service as svc

router = APIRouter(prefix="/incentive", tags=["incentive"])


@router.get("/day")
def day_view(d: date = Query(...), _: str = Depends(get_current_email)):
    return guard(svc.day_view, d, fail="인센티브 조회 실패")


@router.get("/month")
def month_board(month: date = Query(...), _: str = Depends(get_current_email)):
    return guard(svc.month_board, month, fail="인센티브 월 조회 실패")


@router.get("/people")
def people_board(month: date = Query(...), _: str = Depends(require_admin)):
    return guard(svc.person_board, month, fail="담당자별 인센티브 조회 실패")


@router.put("/owners/{d}")
def save_owner(d: date, body: OwnerIn, email: str = Depends(require_admin)):
    return guard(svc.save_owner, d, body.manager_id, body.worker_id, memo(body.memo), email,
                 fail="담당자 지정 실패")


@router.get("/rates")
def rates(_: str = Depends(get_current_email)):
    return guard(svc.list_rate_sets, fail="단가표 조회 실패")


@router.post("/rates")
def add_rates(body: RateSetIn, email: str = Depends(require_admin)):
    b = body.model_dump()
    b["memo"] = memo(b.get("memo"))
    return guard(svc.save_rate_set, None, b, email, fail="단가표 저장 실패")


@router.put("/rates/{sid}")
def update_rates(sid: int, body: RateSetIn, email: str = Depends(require_admin)):
    b = body.model_dump()
    b["memo"] = memo(b.get("memo"))
    return guard(svc.save_rate_set, sid, b, email, fail="단가표 저장 실패")


@router.delete("/rates/{sid}")
def delete_rates(sid: int, email: str = Depends(require_admin)):
    return guard(svc.delete_rate_set, sid, email, fail="단가표 삭제 실패")


@router.put("/accounts/{d}")
def save_accounts(d: date, body: AccountsIn, email: str = Depends(require_admin)):
    return guard(svc.save_accounts, d, [i.model_dump() for i in body.items], email, fail="고객사 수 저장 실패")


@router.post("/qty-adjustments")
def add_qty_adj(body: QtyAdjIn, email: str = Depends(require_admin)):
    return guard(svc.add_qty_adj, body.model_dump(), email, fail="제품 수 조정 저장 실패")


@router.post("/qty-adjustments/{aid}/delete")
def delete_qty_adj(aid: int, body: ReasonIn, email: str = Depends(require_admin)):
    return guard(svc.delete_qty_adj, aid, body.reason, email, fail="제품 수 조정 삭제 실패")


@router.post("/exclusions")
def add_exclusion(body: ExclusionIn, email: str = Depends(require_admin)):
    b = body.model_dump()
    b["memo"] = memo(b.get("memo"))
    return guard(svc.add_exclusion, b, email, fail="배송지 제외 실패")


@router.delete("/exclusions/{xid}")
def delete_exclusion(xid: int, email: str = Depends(require_admin)):
    return guard(svc.delete_exclusion, xid, email, fail="배송지 제외 해제 실패")


@router.get("/extra-items")
def extra_items(_: str = Depends(get_current_email)):
    return guard(svc.list_extra_items, fail="특수 수당 품목 조회 실패")


@router.post("/extra-items")
def add_extra_item(body: ExtraItemIn, email: str = Depends(require_admin)):
    return guard(svc.save_extra_item, None, body.model_dump(), email, fail="품목 저장 실패")


@router.put("/extra-items/{iid}")
def update_extra_item(iid: int, body: ExtraItemIn, email: str = Depends(require_admin)):
    return guard(svc.save_extra_item, iid, body.model_dump(), email, fail="품목 저장 실패")


@router.post("/extras")
def add_extra(body: ExtraIn, email: str = Depends(require_admin)):
    b = body.model_dump()
    b["memo"] = memo(b.get("memo"))
    return guard(svc.add_extra, b, email, fail="특수 수당 저장 실패")


@router.put("/extras/{xid}")
def update_extra(xid: int, body: ExtraUpdateIn, email: str = Depends(require_admin)):
    b = body.model_dump()
    b["memo"] = memo(b.get("memo"))
    return guard(svc.update_extra, xid, b, email, fail="특수 수당 수정 실패")


@router.post("/extras/{xid}/delete")
def delete_extra(xid: int, body: ReasonIn, email: str = Depends(require_admin)):
    return guard(svc.delete_extra, xid, body.reason, email, fail="특수 수당 삭제 실패")


@router.post("/holds/{d}")
def add_hold(d: date, body: HoldIn, email: str = Depends(require_admin)):
    return guard(svc.add_hold, d, body.manager_id, body.reason, email, fail="미지급 등록 실패")


@router.post("/holds/{hid}/release")
def release_hold(hid: int, body: ReasonIn, email: str = Depends(require_admin)):
    return guard(svc.release_hold, hid, body.reason, email, fail="미지급 해제 실패")
