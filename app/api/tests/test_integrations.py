import os
import uuid

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from vora_api.auth_routes import _hasher
from vora_api.db import get_admin_engine, get_app_engine
from vora_api.integration_crypto import open_secret
from vora_api.main import app
from vora_api.models import AuditLog, PlatformSetting, Role, Tenant, User, UserRole
from vora_api.settings import get_settings

pytestmark = pytest.mark.skipif(os.getenv("VORA_INTEGRATION") != "1", reason="needs postgres")

SECRET = "sk-sarvam-test-9f3a"


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
        connection.execute(text("TRUNCATE platform_settings"))
        connection.execute(text("TRUNCATE audit_log, user_roles, users, tenants CASCADE"))
    owner.dispose()
    secrets = {name: pyotp.random_base32() for name in ("owner", "admin", "reader", "tenant")}
    with Session(get_admin_engine()) as session:
        tenant_id = uuid.uuid4()
        session.add(Tenant(id=tenant_id, tenant_id=tenant_id, name="Clinic"))
        session.flush()
        users = {
            "owner": User(
                email="owner@example.com",
                full_name="Owner",
                password_hash=_hasher.hash("owner-password"),
                totp_secret=secrets["owner"],
                totp_confirmed=True,
            ),
            "admin": User(
                email="admin@example.com",
                full_name="Platform Admin",
                password_hash=_hasher.hash("admin-password"),
                totp_secret=secrets["admin"],
                totp_confirmed=True,
            ),
            "reader": User(
                email="reader@example.com",
                full_name="Reader",
                password_hash=_hasher.hash("reader-password"),
                totp_secret=secrets["reader"],
                totp_confirmed=True,
            ),
            "tenant": User(
                email="staff@example.com",
                full_name="Tenant Admin",
                password_hash=_hasher.hash("staff-password"),
                totp_secret=secrets["tenant"],
                totp_confirmed=True,
                tenant_id=tenant_id,
            ),
        }
        session.add_all(users.values())
        session.flush()
        roles = {
            name: session.scalar(select(Role).where(Role.name == name))
            for name in ("Owner", "Platform Admin", "Read-only", "Tenant Admin")
        }
        session.add(UserRole(user_id=users["owner"].id, role_id=roles["Owner"].id, tenant_id=None))
        session.add(
            UserRole(user_id=users["admin"].id, role_id=roles["Platform Admin"].id, tenant_id=None)
        )
        session.add(
            UserRole(user_id=users["reader"].id, role_id=roles["Read-only"].id, tenant_id=None)
        )
        session.add(
            UserRole(
                user_id=users["tenant"].id,
                role_id=roles["Tenant Admin"].id,
                tenant_id=tenant_id,
            )
        )
        session.commit()
    return secrets


def _sign_in(client: TestClient, email: str, password: str) -> None:
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    assert client.cookies.get("vora_access")


def test_owner_saves_a_masked_key_and_the_worker_can_read_it(people: dict[str, str]) -> None:
    del people
    with TestClient(app) as owner:
        _sign_in(owner, "owner@example.com", "owner-password")
        saved = owner.put(
            "/admin/settings/integrations/sarvam",
            json={
                "api_key": SECRET,
                "stt_model": "saaras:v4",
                "tts_model": "bulbul:v3",
                "llm_model": "sarvam-105b-conversations",
            },
        )
        assert saved.status_code == 200
        assert SECRET not in saved.text
        body = saved.json()["sarvam"]
        assert body["api_key_set"] is True
        assert body["api_key_last4"] == "9f3a"
        assert "api_key" not in body
        listed = owner.get("/admin/settings/integrations")
        assert listed.status_code == 200
        assert SECRET not in listed.text
        assert listed.json()["sarvam"]["api_key_last4"] == "9f3a"

    with Session(get_admin_engine()) as session:
        row = session.get(PlatformSetting, "sarvam")
        assert row is not None
        assert row.secret_ciphertext is not None
        assert SECRET not in row.secret_ciphertext
        assert open_secret(row.secret_ciphertext, purpose="sarvam") == SECRET
        audit = session.scalar(
            select(AuditLog).where(AuditLog.action == "update_sarvam_integration")
        )
        assert audit is not None
        assert audit.detail == "sarvam"
        assert SECRET not in (audit.detail or "")

    with TestClient(app) as worker:
        runtime = worker.get("/internal/integrations/sarvam")
        assert runtime.status_code == 200
        assert runtime.json()["api_key"] == SECRET
        assert runtime.json()["source"] == "settings"
        assert runtime.json()["llm_model"] == "sarvam-105b-conversations"


def test_model_change_keeps_the_saved_key(people: dict[str, str]) -> None:
    del people
    with TestClient(app) as owner:
        _sign_in(owner, "owner@example.com", "owner-password")
        assert (
            owner.put("/admin/settings/integrations/sarvam", json={"api_key": SECRET}).status_code
            == 200
        )
        updated = owner.put("/admin/settings/integrations/sarvam", json={"llm_model": "sarvam-30b"})
        assert updated.status_code == 200
        assert updated.json()["sarvam"]["api_key_last4"] == "9f3a"
        assert updated.json()["sarvam"]["llm_model"] == "sarvam-30b"
        assert SECRET not in updated.text
    with Session(get_admin_engine()) as session:
        row = session.get(PlatformSetting, "sarvam")
        assert row is not None
        assert open_secret(row.secret_ciphertext or "", purpose="sarvam") == SECRET


def test_platform_admin_can_save_and_other_roles_cannot(people: dict[str, str]) -> None:
    del people
    with TestClient(app) as admin:
        _sign_in(admin, "admin@example.com", "admin-password")
        saved = admin.put(
            "/admin/settings/integrations/sarvam", json={"api_key": "sk-admin-key-abcd"}
        )
        assert saved.status_code == 200
        assert saved.json()["sarvam"]["api_key_last4"] == "abcd"
    with TestClient(app) as reader:
        _sign_in(reader, "reader@example.com", "reader-password")
        assert reader.get("/admin/settings/integrations").status_code == 403
        assert (
            reader.put("/admin/settings/integrations/sarvam", json={"api_key": SECRET}).status_code
            == 403
        )
    with TestClient(app) as staff:
        _sign_in(staff, "staff@example.com", "staff-password")
        assert staff.get("/admin/settings/integrations").status_code == 403


def test_a_short_key_is_rejected(people: dict[str, str]) -> None:
    del people
    with TestClient(app) as owner:
        _sign_in(owner, "owner@example.com", "owner-password")
        rejected = owner.put("/admin/settings/integrations/sarvam", json={"api_key": "short"})
        assert rejected.status_code == 422


def test_env_key_is_only_a_fallback(
    people: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    del people
    monkeypatch.setenv("SARVAM_API_KEY", "env-sarvam-key-zzzz")
    get_settings.cache_clear()
    try:
        with TestClient(app) as owner:
            _sign_in(owner, "owner@example.com", "owner-password")
            listed = owner.get("/admin/settings/integrations")
            assert listed.json()["sarvam"]["api_key_set"] is False
            assert listed.json()["sarvam"]["env_fallback"] is True
            assert "zzzz" not in listed.text
        with TestClient(app) as worker:
            fallback = worker.get("/internal/integrations/sarvam")
            assert fallback.json()["api_key"] == "env-sarvam-key-zzzz"
            assert fallback.json()["source"] == "env"
        with TestClient(app) as owner:
            _sign_in(owner, "owner@example.com", "owner-password")
            owner.put("/admin/settings/integrations/sarvam", json={"api_key": SECRET})
        with TestClient(app) as worker:
            saved = worker.get("/internal/integrations/sarvam")
            assert saved.json()["api_key"] == SECRET
            assert saved.json()["source"] == "settings"
    finally:
        monkeypatch.delenv("SARVAM_API_KEY", raising=False)
        get_settings.cache_clear()


def test_worker_header_is_required_when_internal_auth_is_set(
    people: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    del people
    monkeypatch.setenv("INTERNAL_AUTH_SECRET", "s3cret")
    get_settings.cache_clear()
    try:
        with TestClient(app) as worker:
            missing = worker.get("/internal/integrations/sarvam")
            assert missing.status_code == 401
            present = worker.get(
                "/internal/integrations/sarvam", headers={"x-vora-internal": "s3cret"}
            )
            assert present.status_code == 200
    finally:
        monkeypatch.delenv("INTERNAL_AUTH_SECRET", raising=False)
        get_settings.cache_clear()


def test_tenant_role_cannot_read_the_ciphertext(people: dict[str, str]) -> None:
    del people
    with TestClient(app) as owner:
        _sign_in(owner, "owner@example.com", "owner-password")
        owner.put("/admin/settings/integrations/sarvam", json={"api_key": SECRET})
    with Session(get_app_engine()) as session:
        with pytest.raises(DBAPIError):
            session.execute(text("SELECT secret_ciphertext FROM platform_settings")).all()
