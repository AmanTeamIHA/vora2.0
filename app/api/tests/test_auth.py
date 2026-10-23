import os

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from vora_api.auth_routes import _hasher
from vora_api.db import get_admin_engine
from vora_api.main import app
from vora_api.models import AuditLog, Role, User, UserRole
from vora_api.settings import get_settings

pytestmark = pytest.mark.skipif(os.getenv("VORA_INTEGRATION") != "1", reason="needs postgres")


@pytest.fixture(scope="module", autouse=True)
def migrated() -> None:
    from alembic import command
    from alembic.config import Config

    get_settings.cache_clear()
    get_admin_engine.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    get_admin_engine.cache_clear()


@pytest.fixture
def accounts() -> dict[str, str]:
    owner = create_engine(get_settings().database_url)
    with owner.begin() as connection:
        connection.execute(text("TRUNCATE audit_log, user_roles, users CASCADE"))
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
        reader_id = reader.id
        session.commit()
    return {
        "owner_secret": owner_secret,
        "reader_secret": reader_secret,
        "reader_id": str(reader_id),
    }


def _sign_in(client: TestClient, email: str, password: str, secret: str) -> None:
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    assert login.json()["totp_required"] is True
    assert "vora_access" not in client.cookies
    totp = client.post("/auth/totp", json={"code": pyotp.TOTP(secret).now()})
    assert totp.status_code == 200
    assert client.cookies.get("vora_access")


def test_read_only_cannot_grant_roles(accounts: dict[str, str]) -> None:
    client = TestClient(app)
    _sign_in(client, "reader@example.com", "reader-password", accounts["reader_secret"])
    denied = client.post(
        "/admin/user-roles",
        json={"user_id": accounts["reader_id"], "role_name": "Support"},
    )
    assert denied.status_code == 403


def test_owner_grant_is_audited_and_logout_clears_session(accounts: dict[str, str]) -> None:
    client = TestClient(app)
    _sign_in(client, "owner@example.com", "owner-password", accounts["owner_secret"])
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["can_write"] is True

    granted = client.post(
        "/admin/user-roles",
        json={"user_id": accounts["reader_id"], "role_name": "Support"},
    )
    assert granted.status_code == 200

    logged_out = client.post("/auth/logout")
    assert logged_out.status_code == 200
    assert client.cookies.get("vora_access") is None
    blocked = client.post(
        "/admin/user-roles",
        json={"user_id": accounts["reader_id"], "role_name": "Finance"},
    )
    assert blocked.status_code == 401

    with Session(get_admin_engine()) as session:
        actions = set(session.scalars(select(AuditLog.action)).all())
    assert {"login", "grant_role", "logout"} <= actions


def test_wrong_password_is_rejected(accounts: dict[str, str]) -> None:
    client = TestClient(app)
    response = client.post(
        "/auth/login",
        json={"email": "owner@example.com", "password": "nope"},
    )
    assert response.status_code == 401
    with Session(get_admin_engine()) as session:
        actions = list(session.scalars(select(AuditLog.action)).all())
    assert "login_failed" in actions
