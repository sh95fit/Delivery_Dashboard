import os

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.routers import (
    allowlist_routes, auth_routes, health_routes, me_routes,
)

app = FastAPI(title="Delivery Dashboard API", version="0.4.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("APP_SECRET", "dev-secret-change-me"),
    max_age=60 * 60 * 24 * 7,
)

app.include_router(health_routes.router)
app.include_router(auth_routes.router)
app.include_router(me_routes.router)
app.include_router(allowlist_routes.router)
