import os

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from fastapi.openapi.utils import get_openapi

from app.routers import (
    allowlist_routes, auth_routes, delivery_routes, health_routes,
    incentive_routes, me_routes, revenue_routes, status_routes,
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
app.include_router(delivery_routes.router)
app.include_router(revenue_routes.router)
app.include_router(status_routes.router)
app.include_router(incentive_routes.router)


def _custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
    schema["servers"] = [{"url": "/api"}]
    schema.setdefault("components", {})
    schema["components"]["securitySchemes"] = {
        "InternalToken": {
            "type": "apiKey",
            "in": "header",
            "name": "X-Internal-Token",
            "description": "서버 .env의 INTERNAL_API_TOKEN 값 입력",
        }
    }
    for path in schema["paths"].values():
        for op in path.values():
            op.setdefault("security", []).append({"InternalToken": []})
    app.openapi_schema = schema
    return schema


app.openapi = _custom_openapi
