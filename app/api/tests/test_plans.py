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
from vora_api.models import Role, TenantLimit, User, UserRole
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
                "TRUNCATE audit_log, tenant_limits, tenant_invites, "
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
            for name in ("Owner", "Read-only", "Tenant Admin")
        }
        session.add(UserRole(user_id=owner_user.id, role_id=roles["Owner"].id, tenant_id=None))
        session.add(UserRole(user_id=reader.id, role_id=roles["Read-only"].id, tenant_id=None))
        session.commit()
    return {"owner_secret": owner_secret, "reader_secret": reader_secret}


def _sign_in(client: TestClient, email: str, password: str, secret: str) -> None:
    assert (
        client.post("/auth/login", json={"email": email, "password": password}).status_code == 200
    )
    assert client.post("/auth/totp", json={"code": pyotp.TOTP(secret).now()}).status_code == 200


def _plan() -> dict[str, object]:
    return {
        "name": "Growth",
        "per_minute_rate_paise": 150,
        "transfer_leg_rate_paise": 80,
        "max_concurrent_calls": 4,
        "max_outbound_share_percent": 60,
        "max_agents": 10,
        "languages": ["hi", "en"],
        "feature_flags": {"transfer": True},
    }


def test_effective_limits_use_plan_then_overrides(people: dict[str, str]) -> None:
    with TestClient(app) as owner:
        _sign_in(owner, "owner@example.com", "owner-password", people["owner_secret"])
        created = owner.post("/admin/plans", json=_plan())
        assert created.status_code == 200
        tenant = owner.post(
            "/admin/tenants",
            json={
                "name": "Limit Clinic",
                "legal_name": "Limit Clinic Pvt Ltd",
                "gstin": "",
                "contact_name": "Ravi",
                "contact_email": "ravi@limit.test",
                "contact_phone": "",
                "plan_name": "Growth",
            },
        )
        assert tenant.status_code == 200
        tenant_id = tenant.json()["id"]
        plain = owner.get(f"/internal/tenants/{tenant_id}/limits")
        assert plain.status_code == 200
        assert plain.json()["max_concurrent_calls"] == 4
        assert plain.json()["per_minute_rate_paise"] == 150
        assert plain.json()["max_agents"] == 10
        assert plain.json()["languages"] == ["hi", "en"]

        updated = owner.put(
            f"/admin/tenants/{tenant_id}/limits",
            json={
                "max_concurrent_calls": 9,
                "per_minute_rate_paise": 250,
                "transfer_leg_rate_paise": None,
            },
        )
        assert updated.status_code == 200
        effective = owner.get(f"/internal/tenants/{tenant_id}/limits").json()
        assert effective["max_concurrent_calls"] == 9
        assert effective["per_minute_rate_paise"] == 250
        assert effective["transfer_leg_rate_paise"] == 80
        assert effective["max_outbound_share_percent"] == 60

    with TestClient(app) as reader:
        _sign_in(reader, "reader@example.com", "reader-password", people["reader_secret"])
        assert reader.post("/admin/plans", json=_plan()).status_code == 403
        assert reader.get(f"/internal/tenants/{tenant_id}/limits").status_code == 200
        assert (
            reader.put(
                f"/admin/tenants/{tenant_id}/limits", json={"max_concurrent_calls": 1}
            ).status_code
            == 403
        )

    other = uuid.uuid4()
    with Session(get_admin_engine()) as session:
        from vora_api.models import Tenant

        session.add(Tenant(id=other, name="Hidden", slug="hidden-limits"))
        session.flush()
        session.add(TenantLimit(tenant_id=other, max_concurrent_calls=99))
        session.commit()
    with Session(get_app_engine()) as session:
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )
        visible = session.get(TenantLimit, uuid.UUID(tenant_id))
        assert visible is not None
        assert visible.max_concurrent_calls == 9
        assert session.get(TenantLimit, other) is None
