from fastapi import APIRouter, Request

from app.auth import get_current_email, is_admin_email
from app.services import permission_service

router = APIRouter(tags=["me"])


@router.get("/me")
async def me(request: Request):
    email = get_current_email(request)
    sup = permission_service.is_super(email)
    return {"email": email, "is_admin": sup or is_admin_email(email),
            "is_super": sup, "grants": permission_service.perm_of(email)}
