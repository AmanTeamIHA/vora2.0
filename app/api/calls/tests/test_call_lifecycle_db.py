import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(os.getenv("VORA_INTEGRATION") != "1", reason="needs postgres")

_API_ROOT = Path(__file__).resolve().parents[2]


def _owner_url() -> URL:
    return make_url(
        os.environ.get("DATABASE_URL", "postgresql+psycopg://vora:vora@localhost:5432/vora")
    )


@pytest.fixture
def clean_database(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """A database with no app tables, so upgrade/downgrade cannot touch the shared one."""
    url = _owner_url()
    name = f"vora_lc_{uuid.uuid4().hex[:12]}"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    test_url = url.set(database=name).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", test_url)
    from vora_api.settings import get_settings

    get_settings.cache_clear()
    try:
        yield test_url
    finally:
        get_settings.cache_clear()
        admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _public_tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
            return set(rows)
    finally:
        engine.dispose()


def _column_exists(url: str, table: str, column: str) -> bool:
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            found = connection.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = :table AND column_name = :column"
                ),
                {"table": table, "column": column},
            ).scalar()
            return found == 1
    finally:
        engine.dispose()


def test_upgrade_head_then_downgrade_one_on_clean_db(clean_database: str) -> None:
    from alembic import command
    from alembic.config import Config

    from vora_api.settings import get_settings

    get_settings.cache_clear()
    config = Config(str(_API_ROOT / "alembic.ini"))
    previous = os.getcwd()
    os.chdir(_API_ROOT)
    try:
        command.upgrade(config, "head")
        assert {"calls", "call_turns", "call_recordings"} <= _public_tables(clean_database)
        assert _column_exists(clean_database, "calls", "duration_ms")
        assert _column_exists(clean_database, "calls", "end_reason")
        assert _column_exists(clean_database, "call_turns", "stt_ms")
        assert _column_exists(clean_database, "call_turns", "llm_ms")
        assert _column_exists(clean_database, "call_turns", "tts_ms")
        assert _column_exists(clean_database, "call_turns", "ttfw_ms")
        assert _column_exists(clean_database, "call_recordings", "recording_key")

        command.downgrade(config, "-1")
        tables = _public_tables(clean_database)
        assert "calls" in tables
        assert "call_turns" not in tables
        assert "call_recordings" not in tables
        assert not _column_exists(clean_database, "calls", "duration_ms")

        command.upgrade(config, "head")
        assert {"calls", "call_turns", "call_recordings"} <= _public_tables(clean_database)
    finally:
        os.chdir(previous)


@pytest.fixture
def migrated_shared() -> None:
    from alembic import command
    from alembic.config import Config

    from vora_api.db import get_admin_engine, get_app_engine
    from vora_api.settings import get_settings

    get_settings.cache_clear()
    get_app_engine.cache_clear()
    get_admin_engine.cache_clear()
    previous = os.getcwd()
    os.chdir(_API_ROOT)
    try:
        command.upgrade(Config("alembic.ini"), "head")
    finally:
        os.chdir(previous)
    get_app_engine.cache_clear()
    get_admin_engine.cache_clear()


def test_tenant_a_reads_zero_rows_of_tenant_b(migrated_shared: None) -> None:
    from vora_api.db import get_app_engine
    from vora_api.settings import get_settings

    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    owner = create_engine(get_settings().database_url)
    with owner.begin() as connection:
        for tenant_id, name in ((tenant_a, "A"), (tenant_b, "B")):
            agent_id = uuid.uuid4()
            version_id = uuid.uuid4()
            call_id = uuid.uuid4()
            connection.execute(
                text("INSERT INTO tenants (id, name) VALUES (:id, :name)"),
                {"id": tenant_id, "name": name},
            )
            connection.execute(
                text("INSERT INTO agents (id, tenant_id, name) VALUES (:id, :tenant_id, :name)"),
                {"id": agent_id, "tenant_id": tenant_id, "name": name},
            )
            connection.execute(
                text(
                    "INSERT INTO agent_versions (id, tenant_id, agent_id, state, config) "
                    "VALUES (:id, :tenant_id, :agent_id, 'committed', CAST(:config AS json))"
                ),
                {
                    "id": version_id,
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "config": "{}",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO calls "
                    "(id, tenant_id, agent_id, agent_version_id, end_reason, duration_ms) "
                    "VALUES (:id, :tenant_id, :agent_id, :version_id, 'caller_hangup', 1000)"
                ),
                {
                    "id": call_id,
                    "tenant_id": tenant_id,
                    "agent_id": agent_id,
                    "version_id": version_id,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO call_turns "
                    "(tenant_id, call_id, turn_index, stt_ms, llm_ms, tts_ms, ttfw_ms) "
                    "VALUES (:tenant_id, :call_id, 0, 1, 2, 3, 6)"
                ),
                {"tenant_id": tenant_id, "call_id": call_id},
            )
            connection.execute(
                text(
                    "INSERT INTO call_recordings (tenant_id, call_id, recording_key) "
                    "VALUES (:tenant_id, :call_id, :recording_key)"
                ),
                {
                    "tenant_id": tenant_id,
                    "call_id": call_id,
                    "recording_key": f"tenants/{tenant_id}/calls/{call_id}/audio.ogg",
                },
            )
    owner.dispose()

    def counts(tenant_id: uuid.UUID, other: uuid.UUID) -> dict[str, tuple[int, int]]:
        session = Session(get_app_engine())
        try:
            session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )
            found: dict[str, tuple[int, int]] = {}
            for table in ("calls", "call_turns", "call_recordings"):
                own = session.execute(
                    text(f"SELECT count(*) FROM {table} WHERE tenant_id = :tenant_id"),
                    {"tenant_id": tenant_id},
                ).scalar_one()
                leaked = session.execute(
                    text(f"SELECT count(*) FROM {table} WHERE tenant_id = :tenant_id"),
                    {"tenant_id": other},
                ).scalar_one()
                found[table] = (own, leaked)
            return found
        finally:
            session.rollback()
            session.close()

    try:
        seen = counts(tenant_a, tenant_b)
        for table in ("calls", "call_turns", "call_recordings"):
            own, leaked = seen[table]
            assert own == 1
            assert leaked == 0
        reverse = counts(tenant_b, tenant_a)
        assert reverse["calls"] == (1, 0)
    finally:
        cleanup = create_engine(get_settings().database_url)
        with cleanup.begin() as connection:
            for statement in (
                "DELETE FROM call_recordings WHERE tenant_id = :a OR tenant_id = :b",
                "DELETE FROM call_turns WHERE tenant_id = :a OR tenant_id = :b",
                "DELETE FROM calls WHERE tenant_id = :a OR tenant_id = :b",
                "DELETE FROM agent_versions WHERE tenant_id = :a OR tenant_id = :b",
                "DELETE FROM agents WHERE tenant_id = :a OR tenant_id = :b",
                "DELETE FROM tenants WHERE id = :a OR id = :b",
            ):
                connection.execute(text(statement), {"a": tenant_a, "b": tenant_b})
        cleanup.dispose()
