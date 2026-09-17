from fastapi import FastAPI
from app.database import rds_ok

app = FastAPI(title="Delivery Dashboard API", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "app": "delivery-dashboard", "version": app.version}


@app.get("/health/db")
def health_db():
    db_connected = rds_ok()
    return {"status": "ok" if db_connected else "error", "db": "connected" if db_connected else "disconnected"}


@app.get("/")
def root():
    return {"message": "Delivery Dashboard API", "docs": "/docs"}
