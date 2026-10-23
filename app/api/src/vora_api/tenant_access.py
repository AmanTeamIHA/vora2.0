import uuid

from sqlalchemy.orm import Session

from vora_api.models import Tenant


def workspace_suspended(session: Session, tenant_id: uuid.UUID | None) -> bool:
    if tenant_id is None:
        return False
    tenant = session.get(Tenant, tenant_id)
    return tenant is not None and tenant.status == "suspended"


def calls_allowed(session: Session, tenant_id: uuid.UUID) -> bool:
    """Dialer checks this before placing a new call. Suspended tenants are refused."""
    tenant = session.get(Tenant, tenant_id)
    return tenant is not None and tenant.status == "active"
