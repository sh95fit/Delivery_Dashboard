from fastapi import FastAPI

app = FastAPI(title="Delivery Dashboard API", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok", "app": "delivery-dashboard", "version": app.version}


@app.get("/")
def root():
    return {"message": "Delivery Dashboard API", "docs": "/docs"}
