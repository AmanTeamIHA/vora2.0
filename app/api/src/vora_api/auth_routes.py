import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vora_api.db import admin_transaction, get_admin_engine
from vora_api.models import AuditLog, Role, User, UserRole
from vora_api.settings import get_settings
from vora_api.tenant_access import workspace_suspended

router = APIRouter()
_hasher = PasswordHasher()
_WRITE_ROLES = frozenset({"Owner", "Platform Admin"})


class LoginBody(BaseModel):
    email: str
    password: str


class TotpBody(BaseModel):
    code: str


class GrantBody(BaseModel):
    user_id: uuid.UUID
    role_name: str


class AuthUser:
    def __init__(self, user_id: uuid.UUID, email: str, roles: list[str]) -> None:
        self.id = user_id
        self.email = email
        self.roles = roles

    @property
    def can_write(self) -> bool:
        return bool(_WRITE_ROLES.intersection(self.roles))


def _token(payload: dict[str, object], ttl: timedelta) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    body = {**payload, "iat": now, "exp": now + ttl}
    return jwt.encode(body, settings.jwt_secret, algorithm="HS256")


def _decode(token: str) -> dict[str, object]:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])


def _cookie(response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        httponly=True,
        samesite="lax",
        secure=get_settings().app_env != "local",
        path="/",
        max_age=max_age,
    )


def _clear(response: Response, name: str) -> None:
    response.delete_cookie(name, path="/")


def _roles_for(session: Session, user_id: uuid.UUID) -> list[str]:
    rows = session.execute(
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .order_by(Role.name)
    ).scalars()
    return list(rows)


def _audit(session: Session, action: str, actor_user_id: uuid.UUID | None) -> None:
    session.add(AuditLog(action=action, actor_user_id=actor_user_id, tenant_id=None))


def _reject_if_disabled(session: Session, user: User) -> None:
    if not user.disabled:
        return
    _audit(session, "login_failed", user.id)
    session.commit()
    raise HTTPException(status_code=403, detail="This account is disabled")


def _reject_if_suspended(session: Session, user: User) -> None:
    if not workspace_suspended(session, user.tenant_id):
        return
    _audit(session, "login_failed", user.id)
    session.commit()
    raise HTTPException(status_code=403, detail="This workspace is suspended")


def require_user(request: Request) -> AuthUser:
    raw = request.cookies.get("vora_access")
    if not raw:
        raise HTTPException(status_code=401, detail="Sign in required")
    try:
        payload = _decode(raw)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Sign in required") from exc
    if payload.get("purpose") != "access":
        raise HTTPException(status_code=401, detail="Sign in required")
    return AuthUser(
        user_id=uuid.UUID(str(payload["sub"])),
        email=str(payload["email"]),
        roles=list(payload.get("roles") or []),
    )


def require_writer(user: AuthUser = Depends(require_user)) -> AuthUser:
    if not user.can_write:
        raise HTTPException(status_code=403, detail="This role cannot change data")
    return user


@router.post("/auth/login")
def login(body: LoginBody, response: Response) -> dict[str, object]:
    with Session(get_admin_engine()) as session:
        user = session.scalar(select(User).where(User.email == body.email))
        password_ok = False
        if user and user.password_hash:
            try:
                password_ok = _hasher.verify(user.password_hash, body.password)
            except VerifyMismatchError:
                password_ok = False
        if not password_ok or user is None:
            _audit(session, "login_failed", user.id if user else None)
            session.commit()
            raise HTTPException(status_code=401, detail="Email or password is wrong")
        _reject_if_disabled(session, user)
        _reject_if_suspended(session, user)
        if not user.totp_secret:
            user.totp_secret = pyotp.random_base32()
        uri = (
            None
            if user.totp_confirmed
            else pyotp.TOTP(user.totp_secret).provisioning_uri(
                name=user.email, issuer_name="Vora 2.0"
            )
        )
        user_id = user.id
        session.commit()

    _cookie(
        response,
        "vora_pending",
        _token({"sub": str(user_id), "purpose": "totp"}, timedelta(minutes=5)),
        5 * 60,
    )
    payload: dict[str, object] = {"totp_required": True}
    if uri:
        payload["provisioning_uri"] = uri
    return payload


@router.post("/auth/totp")
def confirm_totp(body: TotpBody, request: Request, response: Response) -> dict[str, bool]:
    raw = request.cookies.get("vora_pending")
    if not raw:
        raise HTTPException(status_code=401, detail="Sign in required")
    try:
        pending = _decode(raw)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Sign in required") from exc
    if pending.get("purpose") != "totp":
        raise HTTPException(status_code=401, detail="Sign in required")

    with Session(get_admin_engine()) as session:
        user = session.get(User, uuid.UUID(str(pending["sub"])))
        valid = bool(
            user
            and user.totp_secret
            and pyotp.TOTP(user.totp_secret).verify(body.code, valid_window=1)
        )
        if user is None or not valid:
            _audit(session, "login_failed", user.id if user else None)
            session.commit()
            raise HTTPException(status_code=401, detail="Code is wrong")
        _reject_if_disabled(session, user)
        _reject_if_suspended(session, user)
        user.totp_confirmed = True
        roles = _roles_for(session, user.id)
        _audit(session, "login", user.id)
        email = user.email
        user_id = user.id
        session.commit()

    settings = get_settings()
    _cookie(
        response,
        "vora_access",
        _token(
            {"sub": str(user_id), "email": email, "roles": roles, "purpose": "access"},
            timedelta(minutes=settings.access_ttl_minutes),
        ),
        settings.access_ttl_minutes * 60,
    )
    _cookie(
        response,
        "vora_refresh",
        _token(
            {"sub": str(user_id), "purpose": "refresh"},
            timedelta(days=settings.refresh_ttl_days),
        ),
        settings.refresh_ttl_days * 24 * 60 * 60,
    )
    _clear(response, "vora_pending")
    return {"ok": True}


@router.post("/auth/refresh")
def refresh(request: Request, response: Response) -> dict[str, bool]:
    raw = request.cookies.get("vora_refresh")
    if not raw:
        raise HTTPException(status_code=401, detail="Sign in required")
    try:
        payload = _decode(raw)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Sign in required") from exc
    if payload.get("purpose") != "refresh":
        raise HTTPException(status_code=401, detail="Sign in required")
    user_id = uuid.UUID(str(payload["sub"]))
    with Session(get_admin_engine()) as session:
        user = session.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Sign in required")
        _reject_if_disabled(session, user)
        _reject_if_suspended(session, user)
        roles = _roles_for(session, user.id)
        email = user.email
    settings = get_settings()
    _cookie(
        response,
        "vora_access",
        _token(
            {"sub": str(user_id), "email": email, "roles": roles, "purpose": "access"},
            timedelta(minutes=settings.access_ttl_minutes),
        ),
        settings.access_ttl_minutes * 60,
    )
    return {"ok": True}


@router.post("/auth/logout")
def logout(response: Response, user: AuthUser = Depends(require_user)) -> dict[str, bool]:
    with Session(get_admin_engine()) as session:
        _audit(session, "logout", user.id)
        session.commit()
    _clear(response, "vora_access")
    _clear(response, "vora_refresh")
    _clear(response, "vora_pending")
    return {"ok": True}


@router.get("/auth/me")
def me(user: AuthUser = Depends(require_user)) -> dict[str, object]:
    return {"email": user.email, "roles": user.roles, "can_write": user.can_write}


@router.post("/admin/user-roles")
def grant_role(body: GrantBody, actor: AuthUser = Depends(require_writer)) -> dict[str, str]:
    try:
        with admin_transaction(action="grant_role", actor_user_id=actor.id) as session:
            role = session.scalar(
                select(Role).where(Role.name == body.role_name, Role.scope == "platform")
            )
            if role is None:
                raise HTTPException(status_code=404, detail="Unknown platform role")
            session.add(UserRole(user_id=body.user_id, role_id=role.id, tenant_id=None))
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Role already granted") from exc
    return {"status": "ok"}
