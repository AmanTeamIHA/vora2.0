import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from vora_api.db import admin_transaction, get_admin_engine, get_app_engine
from vora_api.main import app
from vora_api.models import AuditLog, Tenant, User, UserRole
from vora_api.settings import get_settings

pytestmark = pytest.mark.skipif(os.getenv("VORA_INTEGRATION") != "1", reason="needs postgres")


@pytest.fixture(scope="module", autouse=True)
def migrated() -> None:
    from alembic import command
    from alembic.config import Config

    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    get_app_engine.cache_clear()
    get_admin_engine.cache_clear()


@pytest.fixture
def tenants() -> dict[str, uuid.UUID]:
    owner = create_engine(get_settings().database_url)
    with owner.begin() as connection:
        connection.execute(text("TRUNCATE audit_log, user_roles, users, tenants CASCADE"))
        tenant_a = uuid.uuid4()
        tenant_b = uuid.uuid4()
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        connection.execute(
            text("INSERT INTO tenants (id, tenant_id, name) VALUES (:id, :id, :name)"),
            [
                {"id": tenant_a, "name": "A"},
                {"id": tenant_b, "name": "B"},
            ],
        )
        connection.execute(
            text(
                "INSERT INTO users (id, tenant_id, email, full_name) "
                "VALUES (:id, :tenant_id, :email, :full_name)"
            ),
            [
                {"id": user_a, "tenant_id": tenant_a, "email": "a@example.com", "full_name": "A"},
                {"id": user_b, "tenant_id": tenant_b, "email": "b@example.com", "full_name": "B"},
            ],
        )
        role_id = connection.execute(
            text("SELECT id FROM roles WHERE name = 'Tenant Admin'")
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO user_roles (user_id, role_id, tenant_id) "
                "VALUES (:user_id, :role_id, :tenant_id)"
            ),
            [
                {"user_id": user_a, "role_id": role_id, "tenant_id": tenant_a},
                {"user_id": user_b, "role_id": role_id, "tenant_id": tenant_b},
            ],
        )
    owner.dispose()
    return {"a": tenant_a, "b": tenant_b, "user_a": user_a, "user_b": user_b}


def _emails_for(tenant_id: uuid.UUID) -> list[str]:
    session = Session(get_app_engine())
    try:
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
        return list(session.scalars(select(User.email).order_by(User.email)).all())
    finally:
        session.rollback()
        session.close()


def test_tenant_a_cannot_read_tenant_b(tenants: dict[str, uuid.UUID]) -> None:
    assert _emails_for(tenants["a"]) == ["a@example.com"]
    assert _emails_for(tenants["b"]) == ["b@example.com"]

    session = Session(get_app_engine())
    try:
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenants["a"])},
        )
        visible_tenants = list(session.scalars(select(Tenant.id)).all())
        visible_roles = list(session.scalars(select(UserRole.user_id)).all())
        leaked = session.scalar(select(User.email).where(User.id == tenants["user_b"]))
    finally:
        session.rollback()
        session.close()

    assert visible_tenants == [tenants["a"]]
    assert visible_roles == [tenants["user_a"]]
    assert leaked is None


def test_request_header_sets_tenant_scope(tenants: dict[str, uuid.UUID]) -> None:
    client = TestClient(app)
    response = client.get("/users", headers={"X-Tenant-Id": str(tenants["a"])})
    assert response.status_code == 200
    assert [row["email"] for row in response.json()] == ["a@example.com"]

    other = client.get("/users", headers={"X-Tenant-Id": str(tenants["b"])})
    assert [row["email"] for row in other.json()] == ["b@example.com"]

    missing = client.get("/users")
    assert missing.json() == []


def test_admin_bypass_writes_audit_log(tenants: dict[str, uuid.UUID]) -> None:
    with admin_transaction(action="read_users") as session:
        emails = set(session.scalars(select(User.email)).all())
    assert emails == {"a@example.com", "b@example.com"}

    with admin_transaction(action="read_audit") as session:
        actions = set(session.scalars(select(AuditLog.action)).all())
    assert "read_users" in actions

    session = Session(get_app_engine())
    try:
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenants["a"])},
        )
        visible = list(session.scalars(select(AuditLog.action)).all())
    finally:
        session.rollback()
        session.close()
    assert visible == []


def test_app_role_cannot_become_admin() -> None:
    engine = create_engine(get_settings().app_database_url)
    try:
        with pytest.raises(ProgrammingError):
            with engine.connect() as connection:
                connection.execute(text("SET ROLE vora_admin"))
    finally:
        engine.dispose()
