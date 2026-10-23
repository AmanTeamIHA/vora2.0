import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vora_api.auth_routes import AuthUser, require_writer
from vora_api.db import admin_transaction, get_admin_engine
from vora_api.models import CallerIdPool, PhoneNumber, Tenant
from vora_api.plan_routes import require_platform

router = APIRouter()
_E164 = re.compile(r"^\+91[6-9]\d{9}$")
_STATUSES = frozenset({"free", "assigned", "blocked"})


class ImportBody(BaseModel):
    numbers: list[str] = Field(min_length=1, max_length=500)


class NumberPatch(BaseModel):
    status: str
    tenant_id: uuid.UUID | None = None
    inbound_agent_id: uuid.UUID | None = None


class PoolBody(BaseModel):
    tenant_id: uuid.UUID
    name: str = Field(min_length=1, max_length=80)


class PoolNumberBody(BaseModel):
    phone_number_id: uuid.UUID


def _clean(raw: str) -> str:
    value = raw.strip().replace(" ", "")
    if not _E164.fullmatch(value):
        raise HTTPException(status_code=422, detail=f"{raw.strip()} is not an Indian mobile DID")
    return value


def _view(number: PhoneNumber, tenant_name: str | None, pool_name: str | None) -> dict[str, object]:
    return {
        "id": str(number.id),
        "e164": number.e164,
        "status": number.status,
        "tenant_id": str(number.tenant_id) if number.tenant_id else None,
        "tenant_name": tenant_name,
        "pool_id": str(number.pool_id) if number.pool_id else None,
        "pool_name": pool_name,
        "inbound_agent_id": str(number.inbound_agent_id) if number.inbound_agent_id else None,
    }


def resolve_inbound_did(session: Session, e164: str) -> PhoneNumber | None:
    """The inbound dispatch lookup. Free and blocked DIDs do not route a call."""
    number = session.scalar(select(PhoneNumber).where(PhoneNumber.e164 == e164))
    if number is None or number.status != "assigned" or number.tenant_id is None:
        return None
    return number


@router.get("/admin/numbers")
def list_numbers(
    status: str | None = None,
    tenant_id: uuid.UUID | None = None,
    _: AuthUser = Depends(require_platform),
) -> dict[str, object]:
    if status is not None and status not in _STATUSES:
        raise HTTPException(status_code=422, detail="Status is not valid")
    with Session(get_admin_engine()) as session:
        query = (
            select(PhoneNumber, Tenant.name, CallerIdPool.name)
            .join(Tenant, Tenant.id == PhoneNumber.tenant_id, isouter=True)
            .join(CallerIdPool, CallerIdPool.id == PhoneNumber.pool_id, isouter=True)
            .order_by(PhoneNumber.e164)
        )
        if status:
            query = query.where(PhoneNumber.status == status)
        if tenant_id:
            query = query.where(PhoneNumber.tenant_id == tenant_id)
        rows = [
            _view(number, tenant_name, pool_name)
            for number, tenant_name, pool_name in session.execute(query).all()
        ]
    return {"numbers": rows}


@router.post("/admin/numbers/import", status_code=201)
def import_numbers(
    body: ImportBody, actor: AuthUser = Depends(require_writer)
) -> dict[str, object]:
    cleaned = []
    seen = set()
    for raw in body.numbers:
        value = _clean(raw)
        if value not in seen:
            seen.add(value)
            cleaned.append(value)
    with admin_transaction(action="import_numbers", actor_user_id=actor.id) as session:
        existing = set(
            session.scalars(select(PhoneNumber.e164).where(PhoneNumber.e164.in_(cleaned)))
        )
        imported = [value for value in cleaned if value not in existing]
        session.add_all(PhoneNumber(e164=value, status="free") for value in imported)
        session.flush()
    return {"imported": imported, "skipped": sorted(existing)}


@router.patch("/admin/numbers/{number_id}")
def update_number(
    number_id: uuid.UUID,
    body: NumberPatch,
    actor: AuthUser = Depends(require_writer),
) -> dict[str, object]:
    if body.status not in _STATUSES:
        raise HTTPException(status_code=422, detail="Status is not valid")
    if body.status == "assigned" and body.tenant_id is None:
        raise HTTPException(status_code=422, detail="An assigned DID needs a tenant")
    with admin_transaction(
        action="update_number",
        actor_user_id=actor.id,
        record_audit=False,
    ) as session:
        number = session.get(PhoneNumber, number_id)
        if number is None:
            raise HTTPException(status_code=404, detail="Number not found")
        tenant_id = body.tenant_id if body.status != "free" else None
        if tenant_id is not None and session.get(Tenant, tenant_id) is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        if body.status == "free" or (number.pool_id and tenant_id != number.tenant_id):
            number.pool_id = None
        number.status = body.status
        number.tenant_id = tenant_id
        number.inbound_agent_id = body.inbound_agent_id if body.status == "assigned" else None
        session.info["audit_tenant_id"] = number.tenant_id
        session.flush()
        pool_name = None
        if number.pool_id:
            pool_name = session.get(CallerIdPool, number.pool_id).name
        tenant_name = session.get(Tenant, number.tenant_id).name if number.tenant_id else None
        payload = _view(number, tenant_name, pool_name)
    return payload


@router.get("/admin/caller-id-pools")
def list_pools(
    tenant_id: uuid.UUID | None = None,
    _: AuthUser = Depends(require_platform),
) -> dict[str, object]:
    with Session(get_admin_engine()) as session:
        query = select(CallerIdPool).order_by(CallerIdPool.name)
        if tenant_id:
            query = query.where(CallerIdPool.tenant_id == tenant_id)
        pools = [
            {"id": str(pool.id), "tenant_id": str(pool.tenant_id), "name": pool.name}
            for pool in session.scalars(query).all()
        ]
    return {"pools": pools}


@router.post("/admin/caller-id-pools", status_code=201)
def create_pool(body: PoolBody, actor: AuthUser = Depends(require_writer)) -> dict[str, str]:
    with admin_transaction(
        action="create_caller_id_pool",
        actor_user_id=actor.id,
        tenant_id=body.tenant_id,
    ) as session:
        if session.get(Tenant, body.tenant_id) is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        pool = CallerIdPool(tenant_id=body.tenant_id, name=body.name.strip())
        session.add(pool)
        try:
            session.flush()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=409, detail="This tenant already has that pool"
            ) from exc
        return {"id": str(pool.id), "name": pool.name}


@router.post("/admin/caller-id-pools/{pool_id}/numbers", status_code=201)
def add_pool_number(
    pool_id: uuid.UUID,
    body: PoolNumberBody,
    actor: AuthUser = Depends(require_writer),
) -> dict[str, str]:
    with admin_transaction(
        action="add_pool_number",
        actor_user_id=actor.id,
        record_audit=False,
    ) as session:
        pool = session.get(CallerIdPool, pool_id)
        number = session.get(PhoneNumber, body.phone_number_id)
        if pool is None or number is None:
            raise HTTPException(status_code=404, detail="Pool or number not found")
        if number.status != "assigned" or number.tenant_id != pool.tenant_id:
            raise HTTPException(
                status_code=409, detail="Only this tenant's assigned DIDs can join the pool"
            )
        if number.pool_id and number.pool_id != pool.id:
            raise HTTPException(status_code=409, detail="This DID is already in another pool")
        number.pool_id = pool.id
        session.info["audit_tenant_id"] = pool.tenant_id
        session.flush()
    return {"pool_id": str(pool_id), "phone_number_id": str(body.phone_number_id)}


@router.get("/internal/dids/{e164}")
def lookup_did(e164: str, _: AuthUser = Depends(require_platform)) -> dict[str, str | None]:
    value = _clean(e164)
    with Session(get_admin_engine()) as session:
        number = resolve_inbound_did(session, value)
        if number is None:
            raise HTTPException(status_code=404, detail="No tenant owns this DID")
        return {
            "e164": number.e164,
            "tenant_id": str(number.tenant_id),
            "inbound_agent_id": str(number.inbound_agent_id) if number.inbound_agent_id else None,
        }
