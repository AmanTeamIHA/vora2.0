from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from vora_api.db import postgres_ok
from vora_api.redis_client import redis_ok
from vora_api.settings import get_settings

app = FastAPI(title="Vora API", version="0.1.0")
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> JSONResponse:
    current = get_settings()
    postgres = postgres_ok(current)
    redis = redis_ok(current)
    ready = postgres and redis
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ok" if ready else "degraded", "postgres": postgres, "redis": redis},
    )
