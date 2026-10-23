import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from vora_api.db import Base


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=text("now()"))


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    parent_tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str | None] = mapped_column(String(80), unique=True)
    legal_name: Mapped[str] = mapped_column(String(200), server_default=text("''"))
    gstin: Mapped[str | None] = mapped_column(String(15))
    contact_name: Mapped[str] = mapped_column(String(200), server_default=text("''"))
    contact_email: Mapped[str] = mapped_column(String(320), server_default=text("''"))
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), server_default=text("'active'"))
    plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("plans.id"))
    feature_flags: Mapped[dict[str, bool]] = mapped_column(
        JSON, server_default=text("'{}'::json"), default=dict
    )
    created_at: Mapped[datetime] = _created()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_confirmed: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    disabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"), default=False)
    created_at: Mapped[datetime] = _created()


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(80), unique=True)
    scope: Mapped[str] = mapped_column(String(32))


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"))
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roles.id"))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=True
    )


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(80), unique=True)
    per_minute_rate_paise: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    transfer_leg_rate_paise: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    max_concurrent_calls: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    max_outbound_share_percent: Mapped[int] = mapped_column(Integer, server_default=text("100"))
    max_agents: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    languages: Mapped[list[str]] = mapped_column(JSON, server_default=text("'[]'::json"))
    feature_flags: Mapped[dict[str, bool]] = mapped_column(JSON, server_default=text("'{}'::json"))
    created_at: Mapped[datetime] = _created()


class TenantLimit(Base):
    __tablename__ = "tenant_limits"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"), primary_key=True)
    max_concurrent_calls: Mapped[int | None] = mapped_column(Integer)
    per_minute_rate_paise: Mapped[int | None] = mapped_column(Integer)
    transfer_leg_rate_paise: Mapped[int | None] = mapped_column(Integer)


class TenantInvite(Base):
    __tablename__ = "tenant_invites"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"))
    email: Mapped[str] = mapped_column(String(320))
    role_name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created()
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserInvite(Base):
    __tablename__ = "user_invites"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tenants.id"))
    email: Mapped[str] = mapped_column(String(320))
    role_name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created()


class CallerIdPool(Base):
    __tablename__ = "caller_id_pools"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = _created()


class PhoneNumber(Base):
    __tablename__ = "phone_numbers"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("tenants.id"))
    pool_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("caller_id_pools.id"))
    e164: Mapped[str] = mapped_column(String(16), unique=True)
    status: Mapped[str] = mapped_column(String(16), server_default=text("'free'"))
    inbound_agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = _created()


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(200))
    deployed_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agent_versions.id")
    )
    created_at: Mapped[datetime] = _created()


class AgentVersion(Base):
    __tablename__ = "agent_versions"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"))
    agent_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("agents.id"))
    state: Mapped[str] = mapped_column(String(16), server_default=text("'draft'"))
    config: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = _created()


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("tenants.id"))
    agent_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("agents.id"))
    agent_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("agent_versions.id"))
    created_at: Mapped[datetime] = _created()


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = _pk()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tenants.id"), nullable=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()
