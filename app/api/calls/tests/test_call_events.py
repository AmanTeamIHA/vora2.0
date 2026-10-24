"""Consumer tests against a fake Redis stream. Postgres checks are integration-only."""

import logging
import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from calls.consumer import drain
from calls.persist import WaitingForCall, tenant_session
from calls.redis_stream import CALL_EVENTS_GROUP, RedisEventStream, StreamEntry
from contracts import (
    CALLS_EVENTS_STREAM,
    CallAnswered,
    CallCreated,
    CallEnded,
    CallRinging,
    TurnCompleted,
)
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from vora_api.main import app

_AT = datetime(2026, 10, 24, 9, 0, tzinfo=UTC)


class FakeStream:
    """In-memory consumer group: new entries, then pending ones that were not acked."""

    def __init__(self, entries: list[tuple[str, dict[str, str]]]) -> None:
        self._new = list(entries)
        self.pending: dict[str, dict[str, str]] = {}
        self.acked: list[str] = []

    def read_pending(self, *, count: int) -> list[StreamEntry]:
        items = list(self.pending.items())[:count]
        return [StreamEntry(message_id, fields) for message_id, fields in items]

    def read_new(self, *, count: int, block_ms: int | None) -> list[StreamEntry]:
        del block_ms
        batch = self._new[:count]
        del self._new[:count]
        found: list[StreamEntry] = []
        for message_id, fields in batch:
            self.pending[message_id] = fields
            found.append(StreamEntry(message_id, fields))
        return found

    def ack(self, message_id: str) -> None:
        self.pending.pop(message_id, None)
        self.acked.append(message_id)


class _FakeRedis:
    def __init__(self) -> None:
        self.created: list[tuple[object, ...]] = []
        self.reads: list[dict[str, object]] = []
        self.acks: list[tuple[object, ...]] = []
        self.claims: list[tuple[object, ...]] = []

    def xgroup_create(
        self,
        name: str,
        groupname: str,
        id: str = "$",
        mkstream: bool = False,
        entries_read: int | None = None,
    ) -> None:
        del entries_read
        self.created.append((name, groupname, id, mkstream))

    def xreadgroup(
        self,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int | None = None,
        block: int | None = None,
        noack: bool = False,
    ) -> None:
        del consumername, noack
        self.reads.append({"group": groupname, "streams": streams, "count": count, "block": block})

    def xack(self, name: str, groupname: str, *ids: str) -> int:
        self.acks.append((name, groupname, ids))
        return len(ids)

    def xautoclaim(
        self,
        name: str,
        groupname: str,
        consumername: str,
        min_idle_time: int,
        start_id: str = "0-0",
        count: int | None = None,
    ) -> tuple[str, list[object], list[object]]:
        del consumername, start_id, count
        self.claims.append((name, groupname, min_idle_time))
        return ("0-0", [], [])


def _data(event: BaseModel) -> dict[str, str]:
    return {"data": event.model_dump_json()}


def _ids() -> dict[str, UUID]:
    return {
        "tenant_id": uuid.uuid4(),
        "call_id": uuid.uuid4(),
        "agent_id": uuid.uuid4(),
        "agent_version_id": uuid.uuid4(),
    }


def _created(ids: dict[str, UUID], at: datetime) -> CallCreated:
    return CallCreated(
        tenant_id=ids["tenant_id"],
        call_id=ids["call_id"],
        occurred_at=at,
        agent_id=ids["agent_id"],
        agent_version_id=ids["agent_version_id"],
    )


def _ringing(ids: dict[str, UUID], at: datetime) -> CallRinging:
    return CallRinging(tenant_id=ids["tenant_id"], call_id=ids["call_id"], occurred_at=at)


def _answered(ids: dict[str, UUID], at: datetime) -> CallAnswered:
    return CallAnswered(tenant_id=ids["tenant_id"], call_id=ids["call_id"], occurred_at=at)


def _turn(ids: dict[str, UUID], at: datetime, index: int, stt_ms: int) -> TurnCompleted:
    return TurnCompleted(
        tenant_id=ids["tenant_id"],
        call_id=ids["call_id"],
        occurred_at=at,
        turn_index=index,
        stt_ms=stt_ms,
        llm_ms=20 + index,
        tts_ms=30 + index,
        ttfw_ms=40 + index,
    )


def _ended(
    ids: dict[str, UUID],
    at: datetime,
    *,
    recording_key: str | None,
    duration_ms: int = 18000,
) -> CallEnded:
    return CallEnded(
        tenant_id=ids["tenant_id"],
        call_id=ids["call_id"],
        occurred_at=at,
        reason="caller_hangup",
        duration_ms=duration_ms,
        recording_key=recording_key,
    )


@contextmanager
def _unused_session(_tenant_id: UUID) -> Iterator[None]:
    yield None


def test_call_events_consumer_group_on_calls_stream() -> None:
    client = _FakeRedis()
    stream = RedisEventStream(client, consumer="api-1")
    stream.ensure_group()
    assert stream.read_new(count=10, block_ms=None) == []
    assert stream.read_pending(count=10) == []
    stream.ack("9-0")
    assert client.created == [(CALLS_EVENTS_STREAM, CALL_EVENTS_GROUP, "0", True)]
    assert client.reads[0]["streams"] == {CALLS_EVENTS_STREAM: ">"}
    assert client.reads[0]["block"] is None
    assert client.reads[1]["streams"] == {CALLS_EVENTS_STREAM: "0"}
    assert client.claims[0][0] == CALLS_EVENTS_STREAM
    assert client.acks == [(CALLS_EVENTS_STREAM, CALL_EVENTS_GROUP, ("9-0",))]


def test_call_events_parses_flat_and_json_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []

    def fake_apply(_session: object, event: object) -> None:
        seen.append(event)

    monkeypatch.setattr("calls.consumer.apply_event", fake_apply)
    ids = _ids()
    ringing = _ringing(ids, _AT)
    created = _created(ids, _AT)
    turn = _turn(ids, _AT, 0, 11)
    flat_turn = {
        key: value if isinstance(value, str) else str(value)
        for key, value in turn.model_dump(mode="json").items()
    }
    stream = FakeStream(
        [
            ("1-0", {key: str(value) for key, value in ringing.model_dump(mode="json").items()}),
            ("2-0", _data(created)),
            ("3-0", flat_turn),
        ]
    )
    stats = drain(stream, session_factory=_unused_session)
    assert stats.applied == 3
    assert stream.acked == ["1-0", "2-0", "3-0"]
    assert isinstance(seen[0], CallRinging)
    assert isinstance(seen[1], CallCreated)
    parsed_turn = seen[2]
    assert isinstance(parsed_turn, TurnCompleted)
    assert parsed_turn.stt_ms == 11


def test_call_events_malformed_entry_acked(caplog: pytest.LogCaptureFixture) -> None:
    stream = FakeStream(
        [
            ("1-0", {"data": "not-json"}),
            ("2-0", {"data": "{}"}),
            ("3-0", {"nope": "missing body"}),
        ]
    )

    def explode(_tenant_id: UUID) -> None:
        raise AssertionError("malformed entry must not open a session")

    with caplog.at_level(logging.WARNING, logger="calls.consumer"):
        stats = drain(stream, session_factory=explode)  # type: ignore[arg-type]

    assert stats.malformed == 3
    assert stats.acked == 3
    assert stats.applied == 0
    assert stream.acked == ["1-0", "2-0", "3-0"]
    assert stream.pending == {}
    assert "malformed call lifecycle entry 1-0" in caplog.text
    assert "malformed call lifecycle entry 2-0" in caplog.text


def test_call_events_waiting_is_not_acked(monkeypatch: pytest.MonkeyPatch) -> None:
    def waiting(_session: object, event: object) -> None:
        assert isinstance(event, CallAnswered)
        raise WaitingForCall(str(event.call_id))

    monkeypatch.setattr("calls.consumer.apply_event", waiting)
    ids = _ids()
    stream = FakeStream([("1-0", _data(_answered(ids, _AT)))])
    stats = drain(stream, session_factory=_unused_session)
    assert stats.waiting == 1
    assert stats.acked == 0
    assert stream.acked == []
    assert "1-0" in stream.pending


def test_call_events_db_error_is_not_acked(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_session: object, _event: object) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("calls.consumer.apply_event", broken)
    ids = _ids()
    stream = FakeStream([("1-0", _data(_created(ids, _AT)))])
    with pytest.raises(RuntimeError, match="database unavailable"):
        drain(stream, session_factory=_unused_session)
    assert stream.acked == []
    assert "1-0" in stream.pending


def test_call_events_consumer_starts_with_the_api(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    class FakeWorker:
        def start(self) -> None:
            events.append("start")

        def stop(self) -> None:
            events.append("stop")

    monkeypatch.setattr("calls.consumer.CallEventWorker", FakeWorker)
    with TestClient(app):
        assert events == ["start"]
    assert events == ["start", "stop"]


@pytest.fixture(scope="module")
def migrated() -> None:
    if os.getenv("VORA_INTEGRATION") != "1":
        pytest.skip("needs postgres")
    from alembic import command
    from alembic.config import Config

    from vora_api.db import get_admin_engine, get_app_engine
    from vora_api.settings import get_settings

    get_settings.cache_clear()
    get_app_engine.cache_clear()
    get_admin_engine.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    get_app_engine.cache_clear()
    get_admin_engine.cache_clear()


@pytest.fixture
def database(migrated: None) -> Iterator[Engine]:
    del migrated
    from vora_api.db import get_app_engine
    from vora_api.settings import get_settings

    get_app_engine.cache_clear()
    engine = create_engine(get_settings().database_url)
    try:
        yield engine
    finally:
        engine.dispose()


def _seed(engine: Engine, ids: dict[str, UUID], name: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenants (id, name) VALUES (:id, :name)"),
            {"id": ids["tenant_id"], "name": name},
        )
        connection.execute(
            text("INSERT INTO agents (id, tenant_id, name) VALUES (:id, :tenant_id, :name)"),
            {"id": ids["agent_id"], "tenant_id": ids["tenant_id"], "name": name},
        )
        connection.execute(
            text(
                "INSERT INTO agent_versions (id, tenant_id, agent_id, state, config) "
                "VALUES (:id, :tenant_id, :agent_id, 'committed', CAST(:config AS json))"
            ),
            {
                "id": ids["agent_version_id"],
                "tenant_id": ids["tenant_id"],
                "agent_id": ids["agent_id"],
                "config": "{}",
            },
        )


def _cleanup(engine: Engine, tenant_id: UUID) -> None:
    with engine.begin() as connection:
        params = {"tenant_id": tenant_id}
        for statement in (
            "DELETE FROM call_recordings WHERE tenant_id = :tenant_id",
            "DELETE FROM call_turns WHERE tenant_id = :tenant_id",
            "DELETE FROM calls WHERE tenant_id = :tenant_id",
            "DELETE FROM agent_versions WHERE tenant_id = :tenant_id",
            "DELETE FROM agents WHERE tenant_id = :tenant_id",
            "DELETE FROM tenants WHERE id = :tenant_id",
        ):
            connection.execute(text(statement), params)


def _call(engine: Engine, call_id: UUID) -> object:
    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT status, ringing_at, answered_at, ended_at, end_reason, duration_ms, "
                "agent_id, agent_version_id, tenant_id, created_at "
                "FROM calls WHERE id = :id"
            ),
            {"id": call_id},
        ).one()


def _turns(engine: Engine, call_id: UUID) -> list[object]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    "SELECT turn_index, stt_ms, llm_ms, tts_ms, ttfw_ms "
                    "FROM call_turns WHERE call_id = :id ORDER BY turn_index"
                ),
                {"id": call_id},
            ).all()
        )


def _recordings(engine: Engine, call_id: UUID) -> list[str]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                text(
                    "SELECT recording_key FROM call_recordings "
                    "WHERE call_id = :id ORDER BY recording_key"
                ),
                {"id": call_id},
            ).scalars()
        )


def _visible_calls(tenant_id: UUID, call_id: UUID) -> int:
    from vora_api.db import get_app_engine

    session = Session(get_app_engine())
    try:
        session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
        return int(
            session.execute(
                text("SELECT count(*) FROM calls WHERE id = :id"),
                {"id": call_id},
            ).scalar_one()
        )
    finally:
        session.rollback()
        session.close()


def test_call_events_full_lifecycle_persists(database: Engine) -> None:
    ids = _ids()
    _seed(database, ids, "lifecycle")
    recording_key = f"tenants/{ids['tenant_id']}/calls/{ids['call_id']}/audio.ogg"
    created_at = _AT
    ringing_at = _AT + timedelta(seconds=1)
    answered_at = _AT + timedelta(seconds=2)
    turn0_at = _AT + timedelta(seconds=3)
    turn1_at = _AT + timedelta(seconds=4)
    ended_at = _AT + timedelta(seconds=5)
    entries = [
        ("1-0", {"data": "not-json"}),
        ("2-0", _data(_created(ids, created_at))),
        ("3-0", _data(_ringing(ids, ringing_at))),
        ("4-0", _data(_answered(ids, answered_at))),
        ("5-0", _data(_turn(ids, turn0_at, 0, 10))),
        ("6-0", _data(_turn(ids, turn1_at, 1, 12))),
        ("7-0", _data(_ended(ids, ended_at, recording_key=recording_key))),
        ("8-0", _data(_ended(ids, ended_at, recording_key=recording_key))),
    ]
    try:
        stats = drain(FakeStream(entries))
        row = _call(database, ids["call_id"])
        assert stats.malformed == 1
        assert stats.acked == len(entries)
        assert row.status == "ended"
        assert row.ringing_at == ringing_at
        assert row.answered_at == answered_at
        assert row.ended_at == ended_at
        assert row.created_at == created_at
        assert row.end_reason == "caller_hangup"
        assert row.duration_ms == 18000
        assert row.agent_id == ids["agent_id"]
        assert row.agent_version_id == ids["agent_version_id"]
        assert row.tenant_id == ids["tenant_id"]
        assert _turns(database, ids["call_id"]) == [
            (0, 10, 20, 30, 40),
            (1, 12, 21, 31, 41),
        ]
        assert _recordings(database, ids["call_id"]) == [recording_key]
    finally:
        _cleanup(database, ids["tenant_id"])


def test_call_events_duplicate_turn_ignored(database: Engine) -> None:
    ids = _ids()
    _seed(database, ids, "duplicate")
    first = _turn(ids, _AT, 0, 10)
    replay = _turn(ids, _AT + timedelta(seconds=9), 0, 99)
    entries = [
        ("1-0", _data(_created(ids, _AT))),
        ("2-0", _data(first)),
        ("3-0", _data(replay)),
        (
            "4-0",
            _data(
                _ended(
                    ids,
                    _AT + timedelta(seconds=10),
                    recording_key=None,
                    duration_ms=1500,
                )
            ),
        ),
    ]
    stream = FakeStream(entries)
    try:
        drain(stream)
        assert stream.acked == ["1-0", "2-0", "3-0", "4-0"]
        assert stream.pending == {}
        assert _turns(database, ids["call_id"]) == [(0, 10, 20, 30, 40)]
        row = _call(database, ids["call_id"])
        assert row.status == "ended"
        assert row.end_reason == "caller_hangup"
        assert row.duration_ms == 1500
        assert _recordings(database, ids["call_id"]) == []
    finally:
        _cleanup(database, ids["tenant_id"])


def test_call_events_answered_before_created(database: Engine) -> None:
    ids = _ids()
    _seed(database, ids, "outoforder")
    answered_at = _AT + timedelta(seconds=2)
    entries = [
        ("1-0", _data(_answered(ids, answered_at))),
        ("2-0", _data(_created(ids, _AT))),
    ]
    stream = FakeStream(entries)
    try:
        stats = drain(stream)
        row = _call(database, ids["call_id"])
        assert stats.acked == 2
        assert set(stream.acked) == {"1-0", "2-0"}
        assert stream.pending == {}
        assert row.status == "answered"
        assert row.answered_at == answered_at
        assert row.ringing_at is None
        assert row.ended_at is None
        assert row.end_reason is None
        assert row.duration_ms is None
        assert row.agent_id == ids["agent_id"]
        assert row.created_at == _AT
    finally:
        _cleanup(database, ids["tenant_id"])


def test_call_events_rls_tenant_set(database: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = _ids()
    other = uuid.uuid4()
    _seed(database, ids, "tenant-a")
    seen: list[UUID] = []

    @contextmanager
    def spy(tenant_id: UUID) -> Iterator[object]:
        seen.append(tenant_id)
        with tenant_session(tenant_id) as session:
            assert session.execute(text("SELECT current_user")).scalar_one() == "vora_app"
            setting = session.execute(
                text("SELECT current_setting('app.tenant_id', true)")
            ).scalar_one()
            assert setting == str(tenant_id)
            yield session

    monkeypatch.setattr("calls.consumer.tenant_session", spy)
    stream = FakeStream([("1-0", _data(_created(ids, _AT)))])
    try:
        drain(stream)
        assert seen == [ids["tenant_id"]]
        assert stream.acked == ["1-0"]
        assert _visible_calls(ids["tenant_id"], ids["call_id"]) == 1
        assert _visible_calls(other, ids["call_id"]) == 0
    finally:
        _cleanup(database, ids["tenant_id"])
