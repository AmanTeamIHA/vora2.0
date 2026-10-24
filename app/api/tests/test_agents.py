import os

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from vora_api.auth_routes import _hasher
from vora_api.db import get_admin_engine, get_app_engine
from vora_api.main import app
from vora_api.models import AgentVersion, Role, User, UserRole
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
        agents = owner.get("/admin/agents", params={"tenant_id": tenant_id})
        assert agents.status_code == 200
        assert agents.json()["agents"][0]["name"] == "Reception"
        assert agents.json()["agents"][0]["deployed"] is True
        calls = owner.get("/admin/calls", params={"tenant_id": tenant_id})
        assert calls.status_code == 200
        assert len(calls.json()["calls"]) == 2
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
