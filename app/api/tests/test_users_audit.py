import os
import uuid
from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from vora_api.auth_routes import _hasher
from vora_api.db import get_admin_engine, get_app_engine
from vora_api.main import app
from vora_api.models import Role, User, UserInvite, UserRole
from vora_api.settings import get_settings

pytestmark = pytest.mark.skipif(os.getenv("VORA_INTEGRATION") != "1", reason="needs postgres")


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
            text(
                "TRUNCATE audit_log, user_invites, tenant_limits, tenant_invites, "
                "user_roles, users, tenants CASCADE"
            )
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
        )
        reader = User(
            email="reader@example.com",
            full_name="Reader",
            password_hash=_hasher.hash("reader-password"),
            totp_secret=reader_secret,
            totp_confirmed=True,
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


def test_invite_disable_and_audit_show_s2_writes(people: dict[str, str]) -> None:
    with TestClient(app) as owner:
        _sign_in(owner, "owner@example.com", "owner-password", people["owner_secret"])
        invited = owner.post(
            "/admin/users",
            json={"email": "support@example.com", "full_name": "Support", "role_name": "Support"},
        )
        assert invited.status_code == 200
        assert invited.json()["invite"]["role"] == "Support"
        assert len(invited.json()["invite"]["token"]) > 20
        support_id = invited.json()["id"]

        secret = pyotp.random_base32()
        with Session(get_admin_engine()) as session:
            user = session.get(User, uuid.UUID(support_id))
            assert user is not None
            user.password_hash = _hasher.hash("support-password")
            user.totp_secret = secret
            user.totp_confirmed = True
            session.commit()

        with TestClient(app) as support:
            assert (
                support.post(
                    "/auth/login",
                    json={"email": "support@example.com", "password": "support-password"},
                ).status_code
                == 200
            )
        disabled = owner.post(f"/admin/users/{support_id}/disable")
        assert disabled.status_code == 200
        assert disabled.json()["disabled"] is True
        with TestClient(app) as support:
            blocked = support.post(
                "/auth/login",
                json={"email": "support@example.com", "password": "support-password"},
            )
        assert blocked.status_code == 403

        tenant = owner.post(
            "/admin/tenants",
            json={
                "name": "Audit Clinic",
                "legal_name": "Audit Clinic Pvt Ltd",
                "gstin": "",
                "contact_name": "Neha",
                "contact_email": "neha@audit.test",
                "contact_phone": "",
                "plan_name": "Starter",
            },
        )
        assert tenant.status_code == 200
        tenant_id = tenant.json()["id"]
        member = owner.post(
            "/admin/users",
            json={
                "email": "agent@audit.test",
                "full_name": "Agent",
                "role_name": "Tenant Admin",
                "tenant_id": tenant_id,
            },
        )
        assert member.status_code == 200

        created = owner.get("/admin/audit", params={"action": "create_tenant"})
        assert created.status_code == 200
        assert created.json()["entries"][0]["tenant_name"] == "Audit Clinic"
        invited_rows = owner.get(
            "/admin/audit", params={"action": "invite_user", "actor": "owner@"}
        )
        assert {row["action"] for row in invited_rows.json()["entries"]} == {"invite_user"}
        logins = owner.get("/admin/audit", params={"action": "login"})
        assert logins.json()["entries"]
        tomorrow = (datetime.now(UTC) + timedelta(days=1)).date().isoformat()
        assert owner.get("/admin/audit", params={"date_from": tomorrow}).json()["entries"] == []
        exported = owner.get("/admin/audit.csv", params={"action": "create_tenant"})
        assert exported.status_code == 200
        assert "create_tenant" in exported.text
        assert "Audit Clinic" in exported.text
        assert owner.delete("/admin/audit").status_code == 405

    with TestClient(app) as reader:
        _sign_in(reader, "reader@example.com", "reader-password", people["reader_secret"])
        assert reader.get("/admin/audit").status_code == 200
        assert (
            reader.post(
                "/admin/users",
                json={"email": "new@example.com", "full_name": "New", "role_name": "Support"},
            ).status_code
            == 403
        )
        assert reader.post(f"/admin/users/{support_id}/disable").status_code == 403

    with Session(get_admin_engine()) as session:
        with pytest.raises(ProgrammingError):
            session.execute(text("UPDATE audit_log SET action = 'tampered'"))
            session.commit()
        session.rollback()

    with Session(get_app_engine()) as session:
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )
        visible = list(session.scalars(select(UserInvite.email)).all())
        assert visible == ["agent@audit.test"]
