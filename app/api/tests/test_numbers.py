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
from vora_api.models import PhoneNumber, Role, User, UserRole
from vora_api.settings import get_settings

pytestmark = pytest.mark.skipif(os.getenv("VORA_INTEGRATION") != "1", reason="needs postgres")

DID = "+919876543210"
OTHER = "+919876543211"


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


def _sign_in(client: TestClient, email: str, password: str, secret: str) -> None:
    assert (
        client.post("/auth/login", json={"email": email, "password": password}).status_code == 200
    )
    assert client.post("/auth/totp", json={"code": pyotp.TOTP(secret).now()}).status_code == 200


def _tenant(client: TestClient, name: str) -> str:
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
    return created.json()["id"]


def test_import_assign_pool_and_lookup(people: dict[str, str]) -> None:
    with TestClient(app) as owner:
        _sign_in(owner, "owner@example.com", "owner-password", people["owner_secret"])
        assert (
            owner.post("/admin/numbers/import", json={"numbers": ["+1 202 555 0100"]}).status_code
            == 422
        )
        imported = owner.post("/admin/numbers/import", json={"numbers": [DID, f" {DID} ", OTHER]})
        assert imported.status_code == 201
        assert imported.json()["imported"] == [DID, OTHER]
        again = owner.post("/admin/numbers/import", json={"numbers": [DID]})
        assert again.json()["skipped"] == [DID]
        assert again.json()["imported"] == []

        clinic = _tenant(owner, "Number Clinic")
        other = _tenant(owner, "Other Clinic")
        listed = owner.get("/admin/numbers").json()["numbers"]
        by_e164 = {row["e164"]: row for row in listed}
        number_id = by_e164[DID]["id"]
        agent_id = str(uuid.uuid4())
        assigned = owner.patch(
            f"/admin/numbers/{number_id}",
            json={"status": "assigned", "tenant_id": clinic, "inbound_agent_id": agent_id},
        )
        assert assigned.status_code == 200
        assert assigned.json()["tenant_name"] == "Number Clinic"
        lookup = owner.get(f"/internal/dids/{DID}")
        assert lookup.status_code == 200
        assert lookup.json()["tenant_id"] == clinic
        assert lookup.json()["inbound_agent_id"] == agent_id
        assert owner.get(f"/internal/dids/{OTHER}").status_code == 404

        pool = owner.post("/admin/caller-id-pools", json={"tenant_id": clinic, "name": "Sales"})
        assert pool.status_code == 201
        added = owner.post(
            f"/admin/caller-id-pools/{pool.json()['id']}/numbers",
            json={"phone_number_id": number_id},
        )
        assert added.status_code == 201
        wrong = owner.patch(
            f"/admin/numbers/{by_e164[OTHER]['id']}",
            json={"status": "assigned", "tenant_id": other},
        )
        assert wrong.status_code == 200
        rejected = owner.post(
            f"/admin/caller-id-pools/{pool.json()['id']}/numbers",
            json={"phone_number_id": by_e164[OTHER]["id"]},
        )
        assert rejected.status_code == 409

        freed = owner.patch(f"/admin/numbers/{number_id}", json={"status": "free"})
        assert freed.status_code == 200
        assert freed.json()["tenant_id"] is None
        assert freed.json()["pool_id"] is None
        assert owner.get(f"/internal/dids/{DID}").status_code == 404

        blocked = owner.patch(f"/admin/numbers/{number_id}", json={"status": "blocked"})
        assert blocked.status_code == 200
        assert owner.get(f"/internal/dids/{DID}").status_code == 404

    with TestClient(app) as reader:
        _sign_in(reader, "reader@example.com", "reader-password", people["reader_secret"])
        assert reader.get("/admin/numbers").status_code == 200
        assert reader.get(f"/internal/dids/{OTHER}").status_code == 200
        assert reader.post("/admin/numbers/import", json={"numbers": [DID]}).status_code == 403

    with Session(get_app_engine()) as session:
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": clinic},
        )
        visible = session.scalars(select(PhoneNumber.e164)).all()
        assert visible == []
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": other},
        )
        visible = session.scalars(select(PhoneNumber.e164)).all()
        assert visible == [OTHER]
