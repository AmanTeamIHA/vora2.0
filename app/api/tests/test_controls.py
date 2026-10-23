import os

import pyotp
import pytest
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from vora_api.auth_routes import _hasher
from vora_api.control_routes import _GLOBAL_KILL, _tenant_kill
from vora_api.db import get_admin_engine, get_app_engine
from vora_api.main import app
from vora_api.models import Role, User, UserRole
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
                "TRUNCATE audit_log, phone_numbers, caller_id_pools, tenant_limits, "
                "tenant_invites, user_invites, user_roles, users, tenants CASCADE"
            )
        )
    owner.dispose()
    client = Redis.from_url(get_settings().redis_url)
    client.delete(_GLOBAL_KILL)
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
    yield {"owner_secret": owner_secret, "reader_secret": reader_secret}
    client.delete(_GLOBAL_KILL)
    client.close()


def _sign_in(client: TestClient, email: str, password: str, secret: str) -> None:
    assert (
        client.post("/auth/login", json={"email": email, "password": password}).status_code == 200
    )
    assert client.post("/auth/totp", json={"code": pyotp.TOTP(secret).now()}).status_code == 200


def _tenant(client: TestClient, name: str, flags: dict[str, bool]) -> str:
    created = client.post(
        "/admin/tenants",
        json={
            "name": name,
            "legal_name": f"{name} Pvt Ltd",
            "gstin": "",
            "contact_name": "Neha",
            "contact_email": f"{name.lower().replace(' ', '')}@clinic.test",
            "contact_phone": "",
            "plan_name": "Starter",
        },
    )
    assert created.status_code == 200
    tenant_id = created.json()["id"]
    if flags:
        plan = client.post(
            "/admin/plans",
            json={
                "name": f"{name} plan",
                "per_minute_rate_paise": 0,
                "transfer_leg_rate_paise": 0,
                "max_concurrent_calls": 1,
                "max_outbound_share_percent": 100,
                "max_agents": 1,
                "languages": ["hi"],
                "feature_flags": flags,
            },
        )
        assert plan.status_code == 200
        patched = client.patch(
            f"/admin/tenants/{tenant_id}",
            json={"plan_name": f"{name} plan"},
        )
        assert patched.status_code == 200
    return tenant_id


def test_impersonation_flags_and_kill_switch(people: dict[str, str]) -> None:
    with TestClient(app) as owner:
        _sign_in(owner, "owner@example.com", "owner-password", people["owner_secret"])
        clinic = _tenant(owner, "Flag Clinic", {"transfer": True, "recording": True})
        other = _tenant(owner, "Other Clinic", {})
        assert (
            owner.post(
                "/admin/impersonate", json={"tenant_id": clinic, "reason": "short"}
            ).status_code
            == 422
        )
        started = owner.post(
            "/admin/impersonate",
            json={"tenant_id": clinic, "reason": "Checking the clinic setup"},
        )
        assert started.status_code == 200
        me = owner.get("/auth/me").json()
        assert me["impersonation"]["tenant_name"] == "Flag Clinic"
        assert me["impersonation"]["actor_email"] == "owner@example.com"
        flags = owner.put(f"/admin/tenants/{clinic}/flags", json={"flags": {"transfer": False}})
        assert flags.status_code == 200
        assert flags.json()["effective"]["transfer"] is False
        assert flags.json()["effective"]["recording"] is True
        audit = owner.get("/admin/audit?action=impersonate").json()["entries"]
        assert audit[0]["detail"] == "Checking the clinic setup"
        assert audit[0]["actor_email"] == "owner@example.com"
        stamped = owner.get("/admin/audit?action=update_feature_flags").json()["entries"]
        assert stamped[0]["detail"] == "Checking the clinic setup"
        assert stamped[0]["actor_email"] == "owner@example.com"

        allowed = owner.post("/internal/outbound/authorize", json={"tenant_id": clinic})
        assert allowed.status_code == 200
        stopped = owner.put("/admin/kill-switch", json={"scope": "global", "enabled": True})
        assert stopped.status_code == 200
        blocked = owner.post("/internal/outbound/authorize", json={"tenant_id": clinic})
        assert blocked.status_code == 409
        owner.put("/admin/kill-switch", json={"scope": "global", "enabled": False})
        owner.put(
            "/admin/kill-switch",
            json={"scope": "tenant", "enabled": True, "tenant_id": clinic},
        )
        assert (
            owner.post("/internal/outbound/authorize", json={"tenant_id": clinic}).status_code
            == 409
        )
        assert (
            owner.post("/internal/outbound/authorize", json={"tenant_id": other}).status_code == 200
        )
        Redis.from_url(get_settings().redis_url).delete(_tenant_kill(clinic))
        assert owner.delete("/admin/impersonate").status_code == 200
        assert "impersonation" not in owner.get("/auth/me").json()

    with TestClient(app) as reader:
        _sign_in(reader, "reader@example.com", "reader-password", people["reader_secret"])
        assert (
            reader.post(
                "/admin/impersonate",
                json={"tenant_id": clinic, "reason": "Checking the clinic setup"},
            ).status_code
            == 403
        )
        assert (
            reader.put("/admin/kill-switch", json={"scope": "global", "enabled": True}).status_code
            == 403
        )
