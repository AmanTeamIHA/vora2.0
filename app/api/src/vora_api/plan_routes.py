import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vora_api.auth_routes import AuthUser, require_user, require_writer
from vora_api.db import admin_transaction, get_admin_engine
from vora_api.limits import effective_limits
from vora_api.models import Plan, Tenant, TenantLimit

router = APIRouter()
_PLATFORM = frozenset({"Owner", "Platform Admin", "Support", "Finance", "Read-only"})


class PlanBody(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    per_minute_rate_paise: int = Field(ge=0)
    transfer_leg_rate_paise: int = Field(ge=0)
    max_concurrent_calls: int = Field(ge=0)
    max_outbound_share_percent: int = Field(ge=0, le=100)
    max_agents: int = Field(ge=0)
    languages: list[str] = Field(default_factory=list)
    feature_flags: dict[str, bool] = Field(default_factory=dict)


class LimitBody(BaseModel):
    max_concurrent_calls: int | None = Field(default=None, ge=0)
    per_minute_rate_paise: int | None = Field(default=None, ge=0)
    transfer_leg_rate_paise: int | None = Field(default=None, ge=0)


def require_platform(user: AuthUser = Depends(require_user)) -> AuthUser:
    if not _PLATFORM.intersection(user.roles):
        raise HTTPException(status_code=403, detail="Platform role required")
    return user


def _languages(values: list[str]) -> list[str]:
    cleaned = []
    for value in values:
        code = value.strip().lower()
        if not code.isalpha() or not 2 <= len(code) <= 8:
            raise HTTPException(status_code=422, detail="Language code is not valid")
        if code not in cleaned:
            cleaned.append(code)
    return cleaned


def _view(plan: Plan) -> dict[str, object]:
    return {
        "id": str(plan.id),
        "name": plan.name,
        "per_minute_rate_paise": plan.per_minute_rate_paise,
        "transfer_leg_rate_paise": plan.transfer_leg_rate_paise,
        "max_concurrent_calls": plan.max_concurrent_calls,
        "max_outbound_share_percent": plan.max_outbound_share_percent,
        "max_agents": plan.max_agents,
        "languages": list(plan.languages or []),
        "feature_flags": dict(plan.feature_flags or {}),
    }


def _apply(plan: Plan, body: PlanBody) -> None:
    plan.name = body.name.strip()
    plan.per_minute_rate_paise = body.per_minute_rate_paise
    plan.transfer_leg_rate_paise = body.transfer_leg_rate_paise
    plan.max_concurrent_calls = body.max_concurrent_calls
    plan.max_outbound_share_percent = body.max_outbound_share_percent
    plan.max_agents = body.max_agents
    plan.languages = _languages(body.languages)
    plan.feature_flags = body.feature_flags


@router.get("/admin/plans")
def list_plans(_user: AuthUser = Depends(require_platform)) -> dict[str, list[dict[str, object]]]:
    with Session(get_admin_engine()) as session:
        plans = session.scalars(select(Plan).order_by(Plan.name)).all()
        return {"plans": [_view(plan) for plan in plans]}


@router.post("/admin/plans")
def create_plan(body: PlanBody, actor: AuthUser = Depends(require_writer)) -> dict[str, object]:
    with admin_transaction(action="create_plan", actor_user_id=actor.id) as session:
        if session.scalar(select(Plan).where(Plan.name == body.name.strip())):
            raise HTTPException(status_code=409, detail="Plan name already exists")
        plan = Plan()
        _apply(plan, body)
        session.add(plan)
        session.flush()
        return _view(plan)


@router.patch("/admin/plans/{plan_id}")
def update_plan(
    plan_id: uuid.UUID, body: PlanBody, actor: AuthUser = Depends(require_writer)
) -> dict[str, object]:
    with admin_transaction(action="update_plan", actor_user_id=actor.id) as session:
        plan = session.get(Plan, plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="Unknown plan")
        _apply(plan, body)
        session.flush()
        return _view(plan)


@router.delete("/admin/plans/{plan_id}")
def delete_plan(plan_id: uuid.UUID, actor: AuthUser = Depends(require_writer)) -> dict[str, str]:
    with admin_transaction(action="delete_plan", actor_user_id=actor.id) as session:
        plan = session.get(Plan, plan_id)
        if plan is None:
            raise HTTPException(status_code=404, detail="Unknown plan")
        in_use = session.scalar(
            select(func.count()).select_from(Tenant).where(Tenant.plan_id == plan_id)
        )
        if in_use:
            raise HTTPException(status_code=409, detail="Plan is assigned to a tenant")
        session.delete(plan)
    return {"status": "ok"}


def _limits(session: Session, tenant_id: uuid.UUID) -> dict[str, object]:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None or tenant.plan_id is None:
        raise HTTPException(status_code=404, detail="Tenant has no plan")
    plan = session.get(Plan, tenant.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Tenant has no plan")
    override = session.get(TenantLimit, tenant_id)
    payload = effective_limits(plan, override, tenant.feature_flags)
    payload["overrides"] = {
        "max_concurrent_calls": None if override is None else override.max_concurrent_calls,
        "per_minute_rate_paise": None if override is None else override.per_minute_rate_paise,
        "transfer_leg_rate_paise": None if override is None else override.transfer_leg_rate_paise,
    }
    return payload


@router.get("/admin/tenants/{tenant_id}/limits")
def tenant_limits(
    tenant_id: uuid.UUID, _user: AuthUser = Depends(require_platform)
) -> dict[str, object]:
    with Session(get_admin_engine()) as session:
        return _limits(session, tenant_id)


@router.put("/admin/tenants/{tenant_id}/limits")
def set_tenant_limits(
    tenant_id: uuid.UUID, body: LimitBody, actor: AuthUser = Depends(require_writer)
) -> dict[str, object]:
    with admin_transaction(
        action="update_tenant_limits", actor_user_id=actor.id, tenant_id=tenant_id
    ) as session:
        if session.get(Tenant, tenant_id) is None:
            raise HTTPException(status_code=404, detail="Unknown tenant")
        row = session.get(TenantLimit, tenant_id)
        if row is None:
            row = TenantLimit(tenant_id=tenant_id)
            session.add(row)
        row.max_concurrent_calls = body.max_concurrent_calls
        row.per_minute_rate_paise = body.per_minute_rate_paise
        row.transfer_leg_rate_paise = body.transfer_leg_rate_paise
        session.flush()
        return _limits(session, tenant_id)


@router.get("/internal/tenants/{tenant_id}/limits")
def internal_limits(
    tenant_id: uuid.UUID, _user: AuthUser = Depends(require_platform)
) -> dict[str, object]:
    with Session(get_admin_engine()) as session:
        payload = _limits(session, tenant_id)
    payload.pop("overrides", None)
    return payload
