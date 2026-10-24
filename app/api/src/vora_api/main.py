import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from vora_api.agent_routes import router as agent_router
from vora_api.auth_routes import router as auth_router
from vora_api.control_routes import impersonation_from_cookie
from vora_api.control_routes import router as control_router
from vora_api.db import get_session, postgres_ok
from vora_api.impersonation import current_impersonation
from vora_api.integration_routes import router as integration_router
from vora_api.models import User
from vora_api.number_routes import router as number_router
from vora_api.plan_routes import router as plan_router
from vora_api.redis_client import redis_ok
from vora_api.settings import get_settings
from vora_api.tenant_context import current_tenant_id
from vora_api.tenant_routes import router as tenant_router
from vora_api.user_routes import router as user_router


def _ensure_calls_package() -> None:
    """Lane C lives in app/api/calls, beside src/. The editable install does not ship it."""
    root = Path(__file__).resolve().parents[2]
    entry = str(root)
    if (root / "calls" / "consumer.py").is_file() and entry not in sys.path:
        sys.path.append(entry)


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _ensure_calls_package()
    from calls.consumer import CallEventWorker

    worker = CallEventWorker()
    worker.start()
    try:
        yield
    finally:
        worker.stop()


app = FastAPI(title="Vora API", version="0.1.0", lifespan=_lifespan)
app.include_router(auth_router)
app.include_router(agent_router)
app.include_router(tenant_router)
app.include_router(plan_router)
app.include_router(user_router)
app.include_router(number_router)
app.include_router(control_router)
app.include_router(integration_router)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


class StripApiPrefix:
    """ALB forwards /api/* to this process. Local clients already omit that prefix."""

    def __init__(self, asgi_app: object) -> None:
        self.asgi_app = asgi_app

    async def __call__(self, scope: dict, receive: object, send: object) -> None:
        if scope.get("type") == "http":
            path = scope.get("path", "")
            if path == "/api":
                scope["path"] = "/"
            elif path.startswith("/api/"):
                scope["path"] = path[4:]
        await self.asgi_app(scope, receive, send)  # type: ignore[misc]


app.add_middleware(StripApiPrefix)


@app.middleware("http")
async def require_internal_secret(request: Request, call_next):
    secret = get_settings().internal_auth_secret
    path = request.url.path
    internal = path.startswith("/internal") or path.startswith("/api/internal")
    if secret and internal:
        if request.headers.get("x-vora-internal") != secret:
            return JSONResponse(status_code=401, content={"detail": "Internal auth failed"})
    return await call_next(request)


@app.middleware("http")
async def bind_tenant(request: Request, call_next):
    token = current_tenant_id.set(request.headers.get("x-tenant-id", "").strip())
    impersonation = current_impersonation.set(
        impersonation_from_cookie(request.cookies.get("vora_impersonate"))
    )
    try:
        return await call_next(request)
    finally:
        current_tenant_id.reset(token)
        current_impersonation.reset(impersonation)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/users")
def list_users(session: Session = Depends(get_session)) -> list[dict[str, str | None]]:
    rows = session.scalars(select(User).order_by(User.email)).all()
    return [
        {
            "id": str(row.id),
            "email": row.email,
            "tenant_id": str(row.tenant_id) if row.tenant_id else None,
        }
        for row in rows
    ]


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
