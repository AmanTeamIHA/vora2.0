import csv
import hashlib
import io
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vora_api.auth_routes import AuthUser, require_user, require_writer
from vora_api.db import admin_transaction, get_admin_engine
from vora_api.models import AuditLog, Role, Tenant, User, UserInvite, UserRole

router = APIRouter()
_PLATFORM = frozenset({"Owner", "Platform Admin", "Support", "Finance", "Read-only"})


class InviteBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    full_name: str = Field(min_length=1, max_length=200)
    role_name: str = Field(min_length=1, max_length=80)
    tenant_id: uuid.UUID | None = None


def require_platform(user: AuthUser = Depends(require_user)) -> AuthUser:
    if not _PLATFORM.intersection(user.roles):
        raise HTTPException(status_code=403, detail="Platform role required")
    return user


def _email(value: str) -> str:
    cleaned = value.strip().lower()
    if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
        raise HTTPException(status_code=422, detail="Email is not valid")
    return cleaned


def _roles(session: Session, user_id: uuid.UUID) -> list[str]:
    rows = session.scalars(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .order_by(Role.name)
    ).all()
    return list(rows)


def _user_view(session: Session, user: User) -> dict[str, object]:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "tenant_id": None if user.tenant_id is None else str(user.tenant_id),
        "disabled": user.disabled,
        "roles": _roles(session, user.id),
    }


@router.get("/admin/users")
def list_users(
    tenant_id: uuid.UUID | None = None,
    _user: AuthUser = Depends(require_platform),
) -> dict[str, list[dict[str, object]]]:
    with Session(get_admin_engine()) as session:
        stmt = select(User).order_by(User.email)
        if tenant_id is None:
            stmt = stmt.where(User.tenant_id.is_(None))
        else:
            stmt = stmt.where(User.tenant_id == tenant_id)
        users = session.scalars(stmt).all()
        return {"users": [_user_view(session, user) for user in users]}


@router.post("/admin/users")
def invite_user(body: InviteBody, actor: AuthUser = Depends(require_writer)) -> dict[str, object]:
    email = _email(body.email)
    scope = "platform" if body.tenant_id is None else "tenant"
    with admin_transaction(
        action="invite_user", actor_user_id=actor.id, tenant_id=body.tenant_id
    ) as session:
        role = session.scalar(select(Role).where(Role.name == body.role_name, Role.scope == scope))
        if role is None:
            raise HTTPException(status_code=404, detail="Unknown role")
        if body.tenant_id is not None and session.get(Tenant, body.tenant_id) is None:
            raise HTTPException(status_code=404, detail="Unknown tenant")
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, full_name=body.full_name.strip(), tenant_id=body.tenant_id)
            session.add(user)
            session.flush()
        elif body.tenant_id is not None and user.tenant_id not in {None, body.tenant_id}:
            raise HTTPException(status_code=409, detail="User belongs to another workspace")
        elif body.tenant_id is not None and user.tenant_id is None:
            raise HTTPException(status_code=409, detail="Platform users are not tenant members")
        session.add(UserRole(user_id=user.id, role_id=role.id, tenant_id=body.tenant_id))
        try:
            session.flush()
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Role already granted") from exc
        raw_token = secrets.token_urlsafe(32)
        session.add(
            UserInvite(
                tenant_id=body.tenant_id,
                email=email,
                role_name=role.name,
                token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            )
        )
        view = _user_view(session, user)
    view["invite"] = {"email": email, "role": body.role_name, "token": raw_token}
    return view


def _set_disabled(user_id: uuid.UUID, disabled: bool, actor: AuthUser) -> dict[str, object]:
    if user_id == actor.id and disabled:
        raise HTTPException(status_code=409, detail="You cannot disable your own account")
    action = "disable_user" if disabled else "enable_user"
    with admin_transaction(action=action, actor_user_id=actor.id, record_audit=False) as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Unknown user")
        user.disabled = disabled
        session.info["audit_tenant_id"] = user.tenant_id
        return _user_view(session, user)


@router.post("/admin/users/{user_id}/disable")
def disable_user(
    user_id: uuid.UUID, actor: AuthUser = Depends(require_writer)
) -> dict[str, object]:
    return _set_disabled(user_id, True, actor)


@router.post("/admin/users/{user_id}/enable")
def enable_user(user_id: uuid.UUID, actor: AuthUser = Depends(require_writer)) -> dict[str, object]:
    return _set_disabled(user_id, False, actor)


def _parse_day(value: str, end: bool) -> datetime:
    try:
        day = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Date must be YYYY-MM-DD") from exc
    if end:
        return day + timedelta(days=1)
    return day


def _audit_rows(
    session: Session,
    *,
    actor: str,
    tenant_id: uuid.UUID | None,
    action: str,
    date_from: str,
    date_to: str,
) -> list[tuple[AuditLog, str | None, str | None]]:
    actor_user = User.__table__.alias("actor_user")
    stmt = (
        select(AuditLog, actor_user.c.email, Tenant.name)
        .outerjoin(actor_user, AuditLog.actor_user_id == actor_user.c.id)
        .outerjoin(Tenant, AuditLog.tenant_id == Tenant.id)
        .order_by(AuditLog.created_at.desc())
    )
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if tenant_id is not None:
        stmt = stmt.where(AuditLog.tenant_id == tenant_id)
    if actor.strip():
        stmt = stmt.where(actor_user.c.email.ilike(f"%{actor.strip()}%"))
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= _parse_day(date_from, end=False))
    if date_to:
        stmt = stmt.where(AuditLog.created_at < _parse_day(date_to, end=True))
    return list(session.execute(stmt.limit(200)).all())


def _entry(row: AuditLog, email: str | None, tenant_name: str | None) -> dict[str, object]:
    return {
        "id": str(row.id),
        "action": row.action,
        "actor_email": email,
        "tenant_id": None if row.tenant_id is None else str(row.tenant_id),
        "tenant_name": tenant_name,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/admin/audit")
def list_audit(
    actor: str = "",
    tenant_id: uuid.UUID | None = None,
    action: str = "",
    date_from: str = "",
    date_to: str = "",
    _user: AuthUser = Depends(require_platform),
) -> dict[str, list[dict[str, object]]]:
    with Session(get_admin_engine()) as session:
        rows = _audit_rows(
            session,
            actor=actor,
            tenant_id=tenant_id,
            action=action,
            date_from=date_from,
            date_to=date_to,
        )
    return {"entries": [_entry(row, email, tenant_name) for row, email, tenant_name in rows]}


@router.get("/admin/audit.csv")
def export_audit(
    actor: str = "",
    tenant_id: uuid.UUID | None = None,
    action: str = "",
    date_from: str = "",
    date_to: str = "",
    _user: AuthUser = Depends(require_platform),
) -> Response:
    with Session(get_admin_engine()) as session:
        rows = _audit_rows(
            session,
            actor=actor,
            tenant_id=tenant_id,
            action=action,
            date_from=date_from,
            date_to=date_to,
        )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["created_at", "action", "actor_email", "tenant_name", "tenant_id"])
    for row, email, tenant_name in rows:
        writer.writerow(
            [
                row.created_at.isoformat(),
                row.action,
                email or "",
                tenant_name or "",
                "" if row.tenant_id is None else str(row.tenant_id),
            ]
        )
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit.csv"},
    )
