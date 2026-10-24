import os
import uuid

import jwt
import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from vora_api.auth_routes import _hasher
from vora_api.db import get_admin_engine, get_app_engine
from vora_api.main import app
from vora_api.models import AgentVersion, AuditLog, Role, User, UserRole
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
                "TRUNCATE audit_log, calls, agent_versions, agents, phone_numbers, "
                "caller_id_pools, tenant_limits, tenant_invites, user_invites, "
                "user_roles, users, tenants CASCADE"
            )
        )
    owner.dispose()
    owner_secret = pyotp.random_base32()
    with Session(get_admin_engine()) as session:
        owner_user = User(
            email="owner@example.com",
            full_name="Owner",
            password_hash=_hasher.hash("owner-password"),
            totp_secret=owner_secret,
            totp_confirmed=True,
        )
        session.add(owner_user)
        session.flush()
        role = session.scalar(select(Role).where(Role.name == "Owner"))
        session.add(UserRole(user_id=owner_user.id, role_id=role.id, tenant_id=None))
        session.commit()
    return {"owner_secret": owner_secret}


def _sign_in(client: TestClient, _secret: str) -> None:
    login = client.post(
        "/auth/login", json={"email": "owner@example.com", "password": "owner-password"}
    )
    assert login.status_code == 200
    assert client.cookies.get("vora_access")


def _version(greeting: str) -> dict[str, object]:
    return {
        "prompt": "Qualify the lead.",
        "greeting": greeting,
        "language": "hi",
        "voice": "meera",
        "tools": [],
        "llm_provider": "sarvam",
    }


def test_deployed_version_is_what_the_next_call_loads(people: dict[str, str]) -> None:
    with TestClient(app) as owner:
        _sign_in(owner, people["owner_secret"])
        tenant = owner.post(
            "/admin/tenants",
            json={
                "name": "Agent Clinic",
                "legal_name": "Agent Clinic Pvt Ltd",
                "gstin": "",
                "contact_name": "Neha",
                "contact_email": "neha@agent.test",
                "contact_phone": "",
                "plan_name": "Starter",
            },
        )
        assert tenant.status_code == 200
        tenant_id = tenant.json()["id"]
        agent = owner.post("/admin/agents", json={"tenant_id": tenant_id, "name": "Reception"})
        assert agent.status_code == 201
        agent_id = agent.json()["id"]
        first = owner.post(f"/admin/agents/{agent_id}/versions", json=_version("Namaste, pehli"))
        second = owner.post(f"/admin/agents/{agent_id}/versions", json=_version("Namaste, doosri"))
        assert first.status_code == 201
        first_id = first.json()["id"]
        second_id = second.json()["id"]
        assert (
            owner.post(
                f"/admin/agents/{agent_id}/deploy", json={"version_id": first_id}
            ).status_code
            == 409
        )
        assert owner.post(f"/admin/agents/{agent_id}/versions/{first_id}/commit").status_code == 200
        assert (
            owner.post(f"/admin/agents/{agent_id}/versions/{second_id}/commit").status_code == 200
        )
        assert (
            owner.post(
                f"/admin/agents/{agent_id}/deploy", json={"version_id": first_id}
            ).status_code
            == 200
        )
        started = owner.post(
            "/internal/calls/start", json={"tenant_id": tenant_id, "agent_id": agent_id}
        )
        assert started.status_code == 201
        assert started.json()["agent_version_id"] == first_id
        assert started.json()["config"]["greeting"] == "Namaste, pehli"
        first_call = started.json()["call_id"]

        assert (
            owner.post(
                f"/admin/agents/{agent_id}/deploy", json={"version_id": second_id}
            ).status_code
            == 200
        )
        nxt = owner.post(
            "/internal/calls/start", json={"tenant_id": tenant_id, "agent_id": agent_id}
        )
        assert nxt.json()["agent_version_id"] == second_id
        assert nxt.json()["config"]["greeting"] == "Namaste, doosri"
        assert owner.get(f"/admin/calls/{first_call}").json()["greeting"] == "Namaste, pehli"
        rejected = _version("Nope")
        rejected["llm_provider"] = "openai"
        assert owner.post(f"/admin/agents/{agent_id}/versions", json=rejected).status_code == 422

    with Session(get_admin_engine()) as session:
        version = session.get(AgentVersion, first_id)
        version.config = {"prompt": "changed"}
        with pytest.raises(DBAPIError):
            session.commit()
    with Session(get_app_engine()) as session:
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": "00000000-0000-0000-0000-000000000000"},
        )
        assert session.get(AgentVersion, first_id) is None


def _deployed_agent(owner: TestClient) -> tuple[str, str]:
    tenant = owner.post(
        "/admin/tenants",
        json={
            "name": "Agent Clinic",
            "legal_name": "Agent Clinic Pvt Ltd",
            "gstin": "",
            "contact_name": "Neha",
            "contact_email": "neha@agent.test",
            "contact_phone": "",
            "plan_name": "Starter",
        },
    )
    assert tenant.status_code == 200
    tenant_id = tenant.json()["id"]
    agent = owner.post("/admin/agents", json={"tenant_id": tenant_id, "name": "Reception"})
    assert agent.status_code == 201
    agent_id = agent.json()["id"]
    version = owner.post(f"/admin/agents/{agent_id}/versions", json=_version("Namaste"))
    assert version.status_code == 201
    version_id = version.json()["id"]
    assert owner.post(f"/admin/agents/{agent_id}/versions/{version_id}/commit").status_code == 200
    assert (
        owner.post(f"/admin/agents/{agent_id}/deploy", json={"version_id": version_id}).status_code
        == 200
    )
    return tenant_id, agent_id


def test_browser_test_session_is_platform_only_and_audited(
    people: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LIVEKIT_URL", "wss://livekit-dev.hellovora.ai")
    monkeypatch.setenv("LIVEKIT_API_KEY", "devkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "secretsecretsecretsecretsecret12")
    get_settings.cache_clear()
    try:
        with TestClient(app) as owner:
            _sign_in(owner, people["owner_secret"])
            tenant_id, agent_id = _deployed_agent(owner)
            minted = owner.post(f"/admin/agents/{agent_id}/test-sessions")
            assert minted.status_code == 201
            body = minted.json()
            assert body["room"].startswith("test-")
            assert body["url"] == "wss://livekit-dev.hellovora.ai"
            claims = jwt.decode(body["token"], options={"verify_signature": False})
            assert claims["video"]["room"] == body["room"]
            metadata = claims["roomConfig"]["metadata"]
            assert tenant_id in metadata and agent_id in metadata
            assert claims["exp"] - claims["nbf"] <= 600
        with Session(get_admin_engine()) as session:
            row = session.scalar(select(AuditLog).where(AuditLog.action == "agent_test_session"))
            assert row is not None
            assert row.tenant_id == uuid.UUID(tenant_id)
            assert str(agent_id) in (row.detail or "")

        with Session(get_admin_engine()) as session:
            tenant_user = User(
                email="staff@agent.test",
                full_name="Staff",
                password_hash=_hasher.hash("staff-password"),
                tenant_id=uuid.UUID(tenant_id),
            )
            session.add(tenant_user)
            session.flush()
            role = session.scalar(select(Role).where(Role.name == "Tenant Admin"))
            session.add(
                UserRole(
                    user_id=tenant_user.id,
                    role_id=role.id,
                    tenant_id=uuid.UUID(tenant_id),
                )
            )
            session.commit()
        with TestClient(app) as staff:
            login = staff.post(
                "/auth/login",
                json={"email": "staff@agent.test", "password": "staff-password"},
            )
            assert login.status_code == 200
            denied = staff.post(f"/admin/agents/{agent_id}/test-sessions")
            assert denied.status_code == 403
    finally:
        get_settings.cache_clear()


def test_worker_starts_a_call_with_the_service_header(
    people: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", "s3cret")
    get_settings.cache_clear()
    try:
        with TestClient(app) as owner:
            _sign_in(owner, people["owner_secret"])
            tenant_id, agent_id = _deployed_agent(owner)
        with TestClient(app) as worker:
            missing = worker.post(
                "/internal/calls/start",
                json={"tenant_id": tenant_id, "agent_id": agent_id},
            )
            assert missing.status_code == 401
            started = worker.post(
                "/internal/calls/start",
                json={"tenant_id": tenant_id, "agent_id": agent_id},
                headers={"x-vora-internal": "s3cret"},
            )
            assert started.status_code == 201
            assert started.json()["config"]["greeting"] == "Namaste"
    finally:
        monkeypatch.delenv("INTERNAL_AUTH_SECRET", raising=False)
        get_settings.cache_clear()


def test_demo_seed_is_idempotent(people: dict[str, str]) -> None:
    from vora_api.models import Agent, Tenant
    from vora_api.seed_demo import AGENT_NAME, GREETING, TENANT_NAME, seed_demo

    seed_demo()
    seed_demo()
    with Session(get_admin_engine()) as session:
        tenants = session.scalars(select(Tenant).where(Tenant.name == TENANT_NAME)).all()
        agents = session.scalars(select(Agent).where(Agent.name == AGENT_NAME)).all()
        assert len(tenants) == 1
        assert len(agents) == 1
        version = session.get(AgentVersion, agents[0].deployed_version_id)
        assert version is not None
        assert version.config["greeting"] == GREETING
        assert version.config["languages"] == ["hi-IN", "en-IN"]
        assert version.config["llm"] == {"provider": "sarvam"}
