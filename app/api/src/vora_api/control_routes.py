import uuid
from datetime import timedelta
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from redis import Redis
from sqlalchemy.orm import Session

from vora_api.auth_routes import AuthUser, _cookie, _decode, _token, require_writer
from vora_api.db import admin_transaction, get_admin_engine
from vora_api.models import Plan, Tenant
from vora_api.plan_routes import require_platform
from vora_api.settings import get_settings
from vora_api.tenant_access import calls_allowed

router = APIRouter()
_GLOBAL_KILL = "kill:outbound:global"
_IMPERSONATE_MINUTES = 30


class ImpersonateBody(BaseModel):
    tenant_id: uuid.UUID
    reason: str = Field(min_length=10, max_length=200)


class FlagBody(BaseModel):
    flags: dict[str, bool]


class KillBody(BaseModel):
    scope: Literal["global", "tenant"]
    enabled: bool
    tenant_id: uuid.UUID | None = None


class OutboundBody(BaseModel):
    tenant_id: uuid.UUID


def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1)


def _tenant_kill(tenant_id: uuid.UUID) -> str:
    return f"kill:outbound:tenant:{tenant_id}"


def outbound_allowed(tenant_id: uuid.UUID) -> bool:
    """Dialer and worker read this before a new outbound call."""
    client = _redis()
    try:
        if client.get(_GLOBAL_KILL):
            return False
        if client.get(_tenant_kill(tenant_id)):
            return False
        return True
    finally:
        client.close()


def impersonation_from_cookie(raw: str | None) -> dict[str, str] | None:
    if not raw:
        return None
    try:
        payload = _decode(raw)
    except jwt.PyJWTError:
        return None
    if payload.get("purpose") != "impersonate":
        return None
    return {
        "tenant_id": str(payload["tenant_id"]),
        "tenant_name": str(payload["tenant_name"]),
        "reason": str(payload["reason"]),
        "actor_email": str(payload["actor_email"]),
    }


@router.post("/admin/impersonate")
def start_impersonation(
    body: ImpersonateBody,
    response: Response,
    actor: AuthUser = Depends(require_writer),
) -> dict[str, object]:
    reason = body.reason.strip()
    if len(reason) < 10:
        raise HTTPException(status_code=422, detail="Give a reason of at least 10 characters")
    with admin_transaction(
        action="impersonate",
        actor_user_id=actor.id,
        tenant_id=body.tenant_id,
        detail=reason,
    ) as session:
        tenant = session.get(Tenant, body.tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail="Unknown tenant")
        name = tenant.name
    _cookie(
        response,
        "vora_impersonate",
        _token(
            {
                "purpose": "impersonate",
                "sub": str(actor.id),
                "tenant_id": str(body.tenant_id),
                "tenant_name": name,
                "reason": reason,
                "actor_email": actor.email,
            },
            timedelta(minutes=_IMPERSONATE_MINUTES),
        ),
        _IMPERSONATE_MINUTES * 60,
    )
    return {
        "tenant_id": str(body.tenant_id),
        "tenant_name": name,
        "reason": reason,
        "minutes": _IMPERSONATE_MINUTES,
    }


@router.delete("/admin/impersonate")
def stop_impersonation(
    request: Request,
    response: Response,
    actor: AuthUser = Depends(require_writer),
) -> dict[str, bool]:
    active = impersonation_from_cookie(request.cookies.get("vora_impersonate"))
    with admin_transaction(
        action="impersonate_stop",
        actor_user_id=actor.id,
        tenant_id=uuid.UUID(active["tenant_id"]) if active else None,
        detail=None if active is None else active["reason"],
    ):
        pass
    response.delete_cookie("vora_impersonate", path="/")
    return {"ok": True}


@router.get("/admin/tenants/{tenant_id}/flags")
def get_flags(tenant_id: uuid.UUID, _: AuthUser = Depends(require_platform)) -> dict[str, object]:
    with Session(get_admin_engine()) as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is None or tenant.plan_id is None:
            raise HTTPException(status_code=404, detail="Unknown tenant")
        plan = session.get(Plan, tenant.plan_id)
        plan_flags = {} if plan is None else dict(plan.feature_flags or {})
        tenant_flags = dict(tenant.feature_flags or {})
    return {
        "plan": plan_flags,
        "tenant": tenant_flags,
        "effective": {**plan_flags, **tenant_flags},
    }


@router.put("/admin/tenants/{tenant_id}/flags")
def set_flags(
    tenant_id: uuid.UUID,
    body: FlagBody,
    actor: AuthUser = Depends(require_writer),
) -> dict[str, object]:
    with admin_transaction(
        action="update_feature_flags",
        actor_user_id=actor.id,
        tenant_id=tenant_id,
    ) as session:
        tenant = session.get(Tenant, tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail="Unknown tenant")
        tenant.feature_flags = body.flags
        session.flush()
    return get_flags(tenant_id, actor)


@router.get("/admin/kill-switch")
def get_kill_switch(
    tenant_id: uuid.UUID | None = None,
    _: AuthUser = Depends(require_platform),
) -> dict[str, bool | None]:
    client = _redis()
    try:
        tenant_on = None if tenant_id is None else bool(client.get(_tenant_kill(tenant_id)))
        return {"global": bool(client.get(_GLOBAL_KILL)), "tenant": tenant_on}
    finally:
        client.close()


@router.put("/admin/kill-switch")
def set_kill_switch(body: KillBody, actor: AuthUser = Depends(require_writer)) -> dict[str, bool]:
    if body.scope == "global":
        key = _GLOBAL_KILL
    elif body.tenant_id is None:
        raise HTTPException(status_code=422, detail="A tenant kill switch needs a tenant")
    else:
        key = _tenant_kill(body.tenant_id)
    with admin_transaction(
        action="kill_switch",
        actor_user_id=actor.id,
        tenant_id=body.tenant_id,
        detail=f"{body.scope} {'on' if body.enabled else 'off'}",
    ):
        client = _redis()
        try:
            if body.enabled:
                client.set(key, "1")
            else:
                client.delete(key)
        finally:
            client.close()
    return {"enabled": body.enabled}


@router.post("/internal/outbound/authorize")
def authorize_outbound(
    body: OutboundBody, _: AuthUser = Depends(require_platform)
) -> dict[str, bool]:
    with Session(get_admin_engine()) as session:
        if not calls_allowed(session, body.tenant_id):
            raise HTTPException(status_code=403, detail="This workspace is suspended")
    if not outbound_allowed(body.tenant_id):
        raise HTTPException(status_code=409, detail="Outbound calls are stopped")
    return {"allowed": True}
