"""라우터 공통 (S1-P1). 권한 세트(P11) 전까지 수정은 ADMIN_EMAILS만."""
import logging

from fastapi import Depends, HTTPException

from app.auth import get_current_email, is_admin_email

logger = logging.getLogger("api")


def require_admin(email: str = Depends(get_current_email)) -> str:
    if not is_admin_email(email):
        raise HTTPException(status_code=403, detail="관리자만 가능합니다")
    return email


def guard(fn, *args, fail: str = "처리 실패"):
    """ValueError → 400(메시지 그대로), 그 외 → 500."""
    try:
        return fn(*args)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception(fail)
        raise HTTPException(status_code=500, detail=f"{fail}: {exc}") from exc


def memo(v: str | None) -> str | None:
    return (v or "").strip() or None
