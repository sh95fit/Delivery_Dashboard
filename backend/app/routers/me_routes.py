from fastapi import APIRouter, Request

from app.auth import get_current_email, is_admin_email

router = APIRouter(tags=["me"])


@router.get("/me")
async def me(request: Request):
    email = get_current_email(request)
    return {"email": email, "is_admin": is_admin_email(email)}
