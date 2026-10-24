"""Persist calls:events into calls, call_turns, and call_recordings.

Entries are acknowledged after the database transaction commits. A malformed
entry is logged and acknowledged so it is not retried forever. An event that
arrives before its call row stays pending and is retried.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
from uuid import UUID

from contracts import LifecycleEvent, parse_lifecycle_event
from pydantic import ValidationError
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from calls.persist import WaitingForCall, apply_event, tenant_session
from calls.redis_stream import RedisEventStream, StreamEntry
from vora_api.settings import get_settings

logger = logging.getLogger(__name__)

_READ_BLOCK_MS = 1000
_BACKOFF_SECONDS = 1.0
_BODY_KEYS = ("data", "payload", "body")

SessionFactory = Callable[[UUID], AbstractContextManager[Session]]


class MalformedEntry(Exception):
    """The stream fields are not a lifecycle event."""


class EventSource(Protocol):
    def read_pending(self, *, count: int) -> list[StreamEntry]: ...

    def read_new(self, *, count: int, block_ms: int | None) -> list[StreamEntry]: ...

    def ack(self, message_id: str) -> None: ...


class Outcome(Enum):
    APPLIED = "applied"
    MALFORMED = "malformed"
    WAITING = "waiting"


@dataclass
class DrainStats:
    applied: int = 0
    malformed: int = 0
    waiting: int = 0
    acked: int = 0


def parse_entry(fields: Mapping[str, str]) -> LifecycleEvent:
    try:
        return parse_lifecycle_event(_payload(fields))
    except ValidationError as exc:
        raise MalformedEntry(str(exc)) from exc


def drain(
    stream: EventSource,
    *,
    session_factory: SessionFactory | None = None,
    block_ms: int | None = None,
    stop: threading.Event | None = None,
    count: int = 50,
) -> DrainStats:
    """Read until the stream is idle. Ack only after a successful commit."""
    factory: SessionFactory = tenant_session if session_factory is None else session_factory
    stats = DrainStats()
    deferred: set[str] = set()
    while stop is None or not stop.is_set():
        pending = [
            entry for entry in stream.read_pending(count=count) if entry.message_id not in deferred
        ]
        if pending:
            batch = pending
        else:
            # Pending rows we cannot apply yet must not block a later call.created.
            batch = stream.read_new(count=count, block_ms=None if deferred else block_ms)
            if not batch:
                return stats
        applied_any = False
        for entry in batch:
            if stop is not None and stop.is_set():
                return stats
            outcome = _handle(entry, factory, stats)
            if outcome is Outcome.WAITING:
                deferred.add(entry.message_id)
                continue
            stream.ack(entry.message_id)
            stats.acked += 1
            deferred.discard(entry.message_id)
            if outcome is Outcome.APPLIED:
                applied_any = True
        if applied_any:
            deferred.clear()
    return stats


class CallEventWorker:
    """Background Redis consumer. start() returns immediately."""

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._redis: Redis | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="call-events", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            client = self._redis
        if client is not None:
            try:
                client.close()
            except RedisError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        url = get_settings().redis_url if self._redis_url is None else self._redis_url
        while not self._stop.is_set():
            client: Redis = Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=None,
            )
            with self._lock:
                self._redis = client
            try:
                if self._stop.is_set():
                    return
                stream = RedisEventStream(client)
                stream.ensure_group()
                while not self._stop.is_set():
                    stats = drain(stream, block_ms=_READ_BLOCK_MS, stop=self._stop)
                    if stats.waiting and stats.applied == 0 and not self._stop.is_set():
                        self._stop.wait(0.5)
            except RedisError as exc:
                logger.warning("call lifecycle consumer redis error: %s", exc)
                if self._stop.wait(_BACKOFF_SECONDS):
                    return
            except Exception:
                logger.exception("call lifecycle consumer failed")
                if self._stop.wait(_BACKOFF_SECONDS):
                    return
            finally:
                with self._lock:
                    if self._redis is client:
                        self._redis = None
                client.close()


def _handle(entry: StreamEntry, session_factory: SessionFactory, stats: DrainStats) -> Outcome:
    try:
        event = parse_entry(entry.fields)
    except MalformedEntry:
        logger.warning("malformed call lifecycle entry %s", entry.message_id, exc_info=True)
        stats.malformed += 1
        return Outcome.MALFORMED
    try:
        with session_factory(event.tenant_id) as session:
            apply_event(session, event)
    except WaitingForCall:
        logger.debug(
            "call lifecycle entry %s waiting for call %s",
            entry.message_id,
            event.call_id,
        )
        stats.waiting += 1
        return Outcome.WAITING
    stats.applied += 1
    return Outcome.APPLIED


def _payload(fields: Mapping[str, str]) -> dict[str, str] | str:
    if "event" in fields:
        return dict(fields)
    for key in _BODY_KEYS:
        body = fields.get(key)
        if body:
            return body
    if len(fields) == 1:
        return next(iter(fields.values()))
    raise MalformedEntry("missing event body")
