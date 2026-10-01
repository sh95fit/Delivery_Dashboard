from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_email, is_admin_email
from app.schemas.internal_target import AddInternalTargetRequest
from app.services import internal_target_service as svc

router = APIRouter(prefix="/internal-targets", tags=["internal-targets"])


def _admin(email: str = Depends(get_current_email)) -> str:
    if not is_admin_email(email):
        raise HTTPException(status_code=403, detail="관리자만 가능합니다")
    return email


@router.get("")
def list_targets(_: str = Depends(get_current_email)):
    try:
        return {"items": svc.list_targets()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"직원식 대상 조회 실패: {exc}") from exc


@router.get("/search")
def search_targets(kind: str = Query(...), q: str = Query(..., min_length=1),
                   _: str = Depends(_admin)):
    try:
        return {"items": svc.search(kind, q)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"검색 실패: {exc}") from exc


@router.post("")
def add_target(body: AddInternalTargetRequest, email: str = Depends(_admin)):
    try:
        new_id = svc.add_target(body.kind, body.target_id, (body.memo or "").strip() or None, email)
        return {"ok": True, "id": new_id}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"등록 실패: {exc}") from exc


@router.delete("/{item_id}")
def delete_target(item_id: int, email: str = Depends(_admin)):
    try:
        svc.delete_target(item_id, email)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"해제 실패: {exc}") from exc
