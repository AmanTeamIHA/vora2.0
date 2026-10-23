import os
import uuid

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from vora_api.auth_routes import _hasher
from vora_api.db import get_admin_engine, get_app_engine
from vora_api.main import app
from vora_api.models import AuditLog, Role, Tenant, TenantInvite, User, UserRole
from vora_api.settings import get_settings
from vora_api.tenant_access import calls_allowed

pytestmark = pytest.mark.skipif(os.getenv("VORA_INTEGRATION") != "1", reason="needs postgres")
_GSTIN = "27AAPFU0939F1ZV"


@pytest.fixture(scope="module", autouse=True)
def migrated() -> None:
    from alembic import command
    from alembic.config import Config

    get_settings.cache_clear()
    get_admin_engine.cache_clear()
    get_app_engine.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    get_admin_engine.cache_clear()
    get_app_engine.cache_clear()


@pytest.fixture
def people() -> dict[str, str]:
    owner = create_engine(get_settings().database_url)
    with owner.begin() as connection:
        connection.execute(
            text("TRUNCATE audit_log, tenant_invites, user_roles, users, tenants CASCADE")
        )
    owner.dispose()

    owner_secret = pyotp.random_base32()
    reader_secret = pyotp.random_base32()
    with Session(get_admin_engine()) as session:
        owner_user = User(
            email="owner@example.com",
            full_name="Owner",
            password_hash=_hasher.hash("owner-password"),
            totp_secret=owner_secret,
            totp_confirmed=True,
            tenant_id=None,
        )
        reader = User(
            email="reader@example.com",
            full_name="Reader",
            password_hash=_hasher.hash("reader-password"),
            totp_secret=reader_secret,
            totp_confirmed=True,
            tenant_id=None,
        )
        session.add_all([owner_user, reader])
        session.flush()
        roles = {
            name: session.scalar(select(Role).where(Role.name == name))
            for name in ("Owner", "Read-only")
        }
        session.add(UserRole(user_id=owner_user.id, role_id=roles["Owner"].id, tenant_id=None))
        session.add(UserRole(user_id=reader.id, role_id=roles["Read-only"].id, tenant_id=None))
        session.commit()
    return {"owner_secret": owner_secret, "reader_secret": reader_secret}


def _sign_in(client: TestClient, email: str, password: str, _secret: str) -> None:
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    assert client.cookies.get("vora_access")


def _body() -> dict[str, str]:
    return {
        "name": "Acme Clinics",
        "legal_name": "Acme Clinics Pvt Ltd",
        "gstin": _GSTIN,
        "contact_name": "Asha Rao",
        "contact_email": "asha@acme.test",
        "contact_phone": "9876543210",
        "plan_name": "Starter",
    }


def test_reader_can_list_and_cannot_change(people: dict[str, str]) -> None:
    with TestClient(app) as owner:
        _sign_in(owner, "owner@example.com", "owner-password", people["owner_secret"])
        created = owner.post("/admin/tenants", json=_body())
        assert created.status_code == 200
    with TestClient(app) as reader:
        _sign_in(reader, "reader@example.com", "reader-password", people["reader_secret"])
        listed = reader.get("/admin/tenants")
        assert listed.status_code == 200
        assert listed.json()["tenants"][0]["name"] == "Acme Clinics"
        assert reader.post("/admin/tenants", json=_body()).status_code == 403
        tenant_id = listed.json()["tenants"][0]["id"]
        assert reader.post(f"/admin/tenants/{tenant_id}/suspend").status_code == 403
        assert (
            reader.patch(f"/admin/tenants/{tenant_id}", json={"legal_name": "Changed"}).status_code
            == 403
        )


def test_owner_creates_invites_and_suspend_blocks_login_and_calls(people: dict[str, str]) -> None:
    with TestClient(app) as owner:
        _sign_in(owner, "owner@example.com", "owner-password", people["owner_secret"])
        created = owner.post("/admin/tenants", json=_body())
        assert created.status_code == 200
        body = created.json()
        assert body["calls_allowed"] is True
        assert body["invite"]["email"] == "asha@acme.test"
        assert body["invite"]["role"] == "Tenant Admin"
        assert len(body["invite"]["token"]) > 20
        tenant_id = uuid.UUID(body["id"])

        listed = owner.get(
            "/admin/tenants", params={"q": _GSTIN, "status": "active", "plan": "Starter"}
        )
        assert [row["id"] for row in listed.json()["tenants"]] == [body["id"]]
        missed = owner.get("/admin/tenants", params={"q": "not-a-tenant"})
        assert missed.json()["tenants"] == []

        edited = owner.patch(
            f"/admin/tenants/{tenant_id}", json={"legal_name": "Acme Health Pvt Ltd"}
        )
        assert edited.status_code == 200
        assert edited.json()["legal_name"] == "Acme Health Pvt Ltd"

        secret = pyotp.random_base32()
        with Session(get_admin_engine()) as session:
            agent = User(
                email="agent@acme.test",
                full_name="Agent",
                password_hash=_hasher.hash("agent-password"),
                totp_secret=secret,
                totp_confirmed=True,
                tenant_id=tenant_id,
            )
            session.add(agent)
            session.flush()
            role = session.scalar(select(Role).where(Role.name == "Tenant Admin"))
            session.add(UserRole(user_id=agent.id, role_id=role.id, tenant_id=tenant_id))
            session.commit()

        suspended = owner.post(f"/admin/tenants/{tenant_id}/suspend")
        assert suspended.status_code == 200
        assert suspended.json()["status"] == "suspended"
        assert suspended.json()["calls_allowed"] is False

    with Session(get_admin_engine()) as session:
        assert calls_allowed(session, tenant_id) is False
        actions = set(session.scalars(select(AuditLog.action)).all())
        assert {"create_tenant", "update_tenant", "suspend_tenant"} <= actions
        invite = session.scalar(select(TenantInvite).where(TenantInvite.tenant_id == tenant_id))
        assert invite is not None
        assert invite.role_name == "Tenant Admin"

    with TestClient(app) as agent_client:
        denied = agent_client.post(
            "/auth/login", json={"email": "agent@acme.test", "password": "agent-password"}
        )
        assert denied.status_code == 403
        assert denied.json()["detail"] == "This workspace is suspended"

    with TestClient(app) as owner:
        _sign_in(owner, "owner@example.com", "owner-password", people["owner_secret"])
        restored = owner.post(f"/admin/tenants/{tenant_id}/reactivate")
        assert restored.json()["calls_allowed"] is True

    with Session(get_admin_engine()) as session:
        assert calls_allowed(session, tenant_id) is True

    other = uuid.uuid4()
    with Session(get_admin_engine()) as session:
        session.add(Tenant(id=other, name="Other", slug="other"))
        session.flush()
        session.add(
            TenantInvite(
                tenant_id=other,
                email="other@example.com",
                role_name="Tenant Admin",
                token_hash="b" * 64,
            )
        )
        session.commit()
    with Session(get_app_engine()) as session:
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
        visible = list(session.scalars(select(TenantInvite.email)).all())
        assert visible == ["asha@acme.test"]
        hidden = session.get(Tenant, other)
        assert hidden is None
