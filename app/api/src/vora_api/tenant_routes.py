import hashlib
import re
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from vora_api.auth_routes import AuthUser, require_user, require_writer
from vora_api.db import admin_transaction, get_admin_engine
from vora_api.models import Plan, Role, Tenant, TenantInvite

router = APIRouter()
_GSTIN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


class TenantBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    legal_name: str = Field(min_length=1, max_length=200)
    gstin: str = ""
    contact_name: str = Field(min_length=1, max_length=200)
    contact_email: str = Field(min_length=3, max_length=320)
    contact_phone: str = ""
    plan_name: str = Field(min_length=1, max_length=80)


class TenantPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, min_length=1, max_length=200)
    gstin: str | None = None
    contact_name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_email: str | None = Field(default=None, min_length=3, max_length=320)
    contact_phone: str | None = None
    plan_name: str | None = Field(default=None, min_length=1, max_length=80)


def _gstin(value: str) -> str | None:
    cleaned = value.strip().upper()
    if not cleaned:
        return None
    if _GSTIN.fullmatch(cleaned) is None:
        raise HTTPException(status_code=422, detail="GSTIN is not valid")
    return cleaned


def _email(value: str) -> str:
    cleaned = value.strip().lower()
    if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
        raise HTTPException(status_code=422, detail="Contact email is not valid")
    return cleaned


def _slug(session: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "tenant"
    taken = set(session.scalars(select(Tenant.slug).where(Tenant.slug.is_not(None))).all())
    slug = base
    suffix = 2
    while slug in taken:
        slug = f"{base[:55]}-{suffix}"
        suffix += 1
    return slug


def _plan(session: Session, name: str) -> Plan:
    plan = session.scalar(select(Plan).where(Plan.name == name))
    if plan is None:
        raise HTTPException(status_code=404, detail="Unknown plan")
    return plan


def _view(tenant: Tenant, plan_name: str | None) -> dict[str, object]:
    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "slug": tenant.slug,
        "legal_name": tenant.legal_name,
        "gstin": tenant.gstin or "",
        "contact_name": tenant.contact_name,
        "contact_email": tenant.contact_email,
        "contact_phone": tenant.contact_phone or "",
        "status": tenant.status,
        "plan": plan_name,
        "calls_allowed": tenant.status == "active",
        "created_at": tenant.created_at.isoformat(),
    }


def _load(session: Session, tenant_id: uuid.UUID) -> tuple[Tenant, str | None]:
    row = session.execute(
        select(Tenant, Plan.name)
        .outerjoin(Plan, Tenant.plan_id == Plan.id)
        .where(Tenant.id == tenant_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown tenant")
    return row


@router.get("/admin/plans")
def list_plans(_user: AuthUser = Depends(require_user)) -> dict[str, list[str]]:
    with Session(get_admin_engine()) as session:
        names = list(session.scalars(select(Plan.name).order_by(Plan.name)).all())
    return {"plans": names}


@router.get("/admin/tenants")
def list_tenants(
    q: str = "",
    status: str = "",
    plan: str = "",
    _user: AuthUser = Depends(require_user),
) -> dict[str, list[dict[str, object]]]:
    if status and status not in {"active", "suspended"}:
        raise HTTPException(status_code=422, detail="Unknown status")
    with Session(get_admin_engine()) as session:
        stmt = select(Tenant, Plan.name).outerjoin(Plan, Tenant.plan_id == Plan.id)
        if q.strip():
            needle = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    Tenant.name.ilike(needle),
                    Tenant.legal_name.ilike(needle),
                    Tenant.gstin.ilike(needle),
                )
            )
        if status:
            stmt = stmt.where(Tenant.status == status)
        if plan:
            stmt = stmt.where(Plan.name == plan)
        rows = session.execute(stmt.order_by(Tenant.name)).all()
    return {"tenants": [_view(tenant, plan_name) for tenant, plan_name in rows]}


@router.post("/admin/tenants")
def create_tenant(body: TenantBody, actor: AuthUser = Depends(require_writer)) -> dict[str, object]:
    gstin = _gstin(body.gstin)
    email = _email(body.contact_email)
    with admin_transaction(
        action="create_tenant", actor_user_id=actor.id, record_audit=False
    ) as session:
        plan = _plan(session, body.plan_name)
        role = session.scalar(
            select(Role).where(Role.name == "Tenant Admin", Role.scope == "tenant")
        )
        if role is None:
            raise HTTPException(status_code=500, detail="Tenant Admin role is missing")
        tenant = Tenant(
            name=body.name.strip(),
            slug=_slug(session, body.name),
            legal_name=body.legal_name.strip(),
            gstin=gstin,
            contact_name=body.contact_name.strip(),
            contact_email=email,
            contact_phone=body.contact_phone.strip() or None,
            status="active",
            plan_id=plan.id,
        )
        session.add(tenant)
        session.flush()
        raw_token = secrets.token_urlsafe(32)
        session.add(
            TenantInvite(
                tenant_id=tenant.id,
                email=email,
                role_name=role.name,
                token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            )
        )
        session.info["audit_tenant_id"] = tenant.id
        view = _view(tenant, plan.name)
    view["invite"] = {"email": email, "role": "Tenant Admin", "token": raw_token}
    return view


@router.patch("/admin/tenants/{tenant_id}")
def update_tenant(
    tenant_id: uuid.UUID,
    body: TenantPatch,
    actor: AuthUser = Depends(require_writer),
) -> dict[str, object]:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Nothing to change")
    with admin_transaction(
        action="update_tenant", actor_user_id=actor.id, tenant_id=tenant_id
    ) as session:
        tenant, _plan_name = _load(session, tenant_id)
        if "name" in changes:
            tenant.name = changes["name"].strip()
        if "legal_name" in changes:
            tenant.legal_name = changes["legal_name"].strip()
        if "gstin" in changes:
            tenant.gstin = _gstin(changes["gstin"] or "")
        if "contact_name" in changes:
            tenant.contact_name = changes["contact_name"].strip()
        if "contact_email" in changes:
            tenant.contact_email = _email(changes["contact_email"])
        if "contact_phone" in changes:
            tenant.contact_phone = (changes["contact_phone"] or "").strip() or None
        if "plan_name" in changes:
            tenant.plan_id = _plan(session, changes["plan_name"]).id
        session.flush()
        plan_name = session.scalar(select(Plan.name).where(Plan.id == tenant.plan_id))
        return _view(tenant, plan_name)


def _set_status(tenant_id: uuid.UUID, status: str, actor: AuthUser) -> dict[str, object]:
    action = "suspend_tenant" if status == "suspended" else "reactivate_tenant"
    with admin_transaction(action=action, actor_user_id=actor.id, tenant_id=tenant_id) as session:
        tenant, plan_name = _load(session, tenant_id)
        tenant.status = status
        session.flush()
        return _view(tenant, plan_name)


@router.post("/admin/tenants/{tenant_id}/suspend")
def suspend_tenant(
    tenant_id: uuid.UUID, actor: AuthUser = Depends(require_writer)
) -> dict[str, object]:
    return _set_status(tenant_id, "suspended", actor)


@router.post("/admin/tenants/{tenant_id}/reactivate")
def reactivate_tenant(
    tenant_id: uuid.UUID, actor: AuthUser = Depends(require_writer)
) -> dict[str, object]:
    return _set_status(tenant_id, "active", actor)
