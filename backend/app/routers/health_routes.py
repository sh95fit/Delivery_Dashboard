from fastapi import APIRouter

from app.database import rds_ok

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    from app.main import app  # 버전 표시용

    return {"status": "ok", "app": "delivery-dashboard", "version": app.version}


@router.get("/health/db")
def health_db():
    return {
        "status": "ok" if rds_ok() else "error",
        "db": "connected" if rds_ok() else "disconnected",
    }
