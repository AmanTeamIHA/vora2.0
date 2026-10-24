"""Publish one call's lifecycle to Redis Streams.

The JSON body is the contracts model. The same bytes go to ``calls:events`` and
``calls:events:{tenant_id}`` under the stream field ``data``. A Redis failure is logged.
It does not propagate into the conversation.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from threading import Lock
from typing import Protocol
from uuid import UUID

from contracts import (
    CALLS_EVENTS_STREAM,
    CallAnswered,
    CallCreated,
    CallEnded,
    CallRinging,
    TurnCompleted,
    parse_lifecycle_event,
    tenant_calls_stream,
)
from redis import Redis

logger = logging.getLogger("vora.agent")

# Worker metric name → turn.completed field. See docs/CALL_CONTRACT.md.
_TURN_FIELDS = (
    ("eos_to_stt_final", "stt_ms"),
    ("llm_first_token", "llm_ms"),
    ("tts_first_byte", "tts_ms"),
    ("time_to_first_word", "ttfw_ms"),
)


class StreamClient(Protocol):
    def xadd(self, name: str, fields: dict[str, str]) -> object: ...


class LifecyclePublisher:
    """Append a validated lifecycle body to the global stream and the tenant stream."""

    def __init__(self, redis: StreamClient | None) -> None:
        self._redis = redis

    @classmethod
    def from_env(cls) -> LifecyclePublisher:
        url = os.environ.get("REDIS_URL", "").strip()
        if not url:
            logger.warning("REDIS_URL is not set; call lifecycle events will not be published")
            return cls(None)
        try:
            client = Redis.from_url(
                url,
                socket_connect_timeout=1,
                socket_timeout=1,
                decode_responses=True,
            )
        except Exception:
            logger.exception("redis client setup failed")
            return cls(None)
        return cls(client)

    def publish(
        self, event: CallCreated | CallRinging | CallAnswered | TurnCompleted | CallEnded
    ) -> None:
        try:
            body = event.model_dump_json()
            parse_lifecycle_event(body)
        except Exception:
            logger.exception("lifecycle event invalid call_id=%s", getattr(event, "call_id", ""))
            return
        if self._redis is None:
            return
        wrote = False
        for stream in (CALLS_EVENTS_STREAM, tenant_calls_stream(event.tenant_id)):
            try:
                self._redis.xadd(stream, {"data": body})
            except Exception:
                logger.exception(
                    "lifecycle publish failed stream=%s event=%s call_id=%s",
                    stream,
                    event.event,
                    event.call_id,
                )
                continue
            wrote = True
        if wrote:
            logger.info("lifecycle_published event=%s call_id=%s", event.event, event.call_id)


class NullLifecycle:
    """Used when the call ids are not UUIDs. The conversation still runs."""

    def created(self) -> None:
        return

    def observe_sip_status(self, status: str) -> None:
        return

    def session_ready(self) -> None:
        return

    def complete_speech(self, speech_id: str, metrics: Mapping[str, int]) -> None:
        return

    def ended(self, reason: str) -> None:
        return


class CallLifecycle:
    """One call. Methods are safe to call more than once; each fact is published once."""

    def __init__(
        self,
        publisher: LifecyclePublisher,
        *,
        tenant_id: UUID,
        call_id: UUID,
        agent_id: UUID,
        agent_version_id: UUID,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._publisher = publisher
        self._tenant_id = tenant_id
        self._call_id = call_id
        self._agent_id = agent_id
        self._agent_version_id = agent_version_id
        self._now = now or (lambda: datetime.now(UTC))
        self._monotonic = monotonic or time.monotonic
        self._lock = Lock()
        self._created = False
        self._ringing = False
        self._answered = False
        self._ended = False
        self._awaiting_sip = False
        self._started: float | None = None
        self._turn_index = 0
        self._speeches: set[str] = set()
        self._buffer: list[TurnCompleted] = []

    def created(self) -> None:
        with self._lock:
            if self._created:
                return
            self._created = True
            self._started = self._monotonic()
            self._publisher.publish(
                CallCreated(
                    tenant_id=self._tenant_id,
                    call_id=self._call_id,
                    occurred_at=self._now(),
                    agent_id=self._agent_id,
                    agent_version_id=self._agent_version_id,
                )
            )

    def observe_sip_status(self, status: str) -> None:
        """LiveKit SIP attribute ``sip.callStatus``. Browser participants have none."""
        with self._lock:
            if not self._created or self._ended:
                return
            if status == "ringing":
                if not self._answered:
                    self._awaiting_sip = True
                self._emit_ringing()
            elif status == "dialing":
                if not self._answered:
                    self._awaiting_sip = True
            elif status == "active":
                self._awaiting_sip = False
                self._emit_answered()

    def session_ready(self) -> None:
        """Answer browser calls. A SIP leg that is still dialing or ringing waits."""
        with self._lock:
            if not self._created or self._ended or self._answered or self._awaiting_sip:
                return
            self._emit_answered()

    def complete_speech(self, speech_id: str, metrics: Mapping[str, int]) -> None:
        with self._lock:
            if not self._created or self._ended or speech_id in self._speeches:
                return
            try:
                event = self._turn(metrics)
            except Exception:
                logger.exception("turn.completed invalid call_id=%s", self._call_id)
                return
            self._speeches.add(speech_id)
            if not self._answered:
                self._buffer.append(event)
                return
            self._publisher.publish(event)

    def ended(self, reason: str) -> None:
        with self._lock:
            if not self._created or self._ended:
                return
            self._ended = True
            if self._buffer:
                logger.info(
                    "dropping %s turn(s) because the call ended before answer call_id=%s",
                    len(self._buffer),
                    self._call_id,
                )
                self._buffer.clear()
            started = self._started if self._started is not None else self._monotonic()
            duration_ms = max(0, int((self._monotonic() - started) * 1000))
            text = reason.strip() or "disconnected"
            self._publisher.publish(
                CallEnded(
                    tenant_id=self._tenant_id,
                    call_id=self._call_id,
                    occurred_at=self._now(),
                    reason=text,
                    duration_ms=duration_ms,
                    recording_key=None,
                )
            )

    def _emit_ringing(self) -> None:
        if self._ringing or self._answered:
            return
        self._ringing = True
        self._publisher.publish(
            CallRinging(
                tenant_id=self._tenant_id,
                call_id=self._call_id,
                occurred_at=self._now(),
            )
        )

    def _emit_answered(self) -> None:
        if self._answered or self._ended or not self._created:
            return
        self._answered = True
        self._awaiting_sip = False
        self._publisher.publish(
            CallAnswered(
                tenant_id=self._tenant_id,
                call_id=self._call_id,
                occurred_at=self._now(),
            )
        )
        pending = self._buffer
        self._buffer = []
        for event in pending:
            self._publisher.publish(event)

    def _turn(self, metrics: Mapping[str, int]) -> TurnCompleted:
        values = {field: _ms(metrics.get(source, 0)) for source, field in _TURN_FIELDS}
        event = TurnCompleted(
            tenant_id=self._tenant_id,
            call_id=self._call_id,
            occurred_at=self._now(),
            turn_index=self._turn_index,
            stt_ms=values["stt_ms"],
            llm_ms=values["llm_ms"],
            tts_ms=values["tts_ms"],
            ttfw_ms=values["ttfw_ms"],
        )
        self._turn_index += 1
        return event


def sip_call_status(attributes: Mapping[str, str] | None) -> str:
    """Read LiveKit's SIP call status. Empty when this participant is not SIP."""
    if not attributes:
        return ""
    return str(attributes.get("sip.callStatus", "") or "")


def open_call_lifecycle(
    publisher: LifecyclePublisher,
    *,
    tenant_id: str,
    call_id: str,
    agent_id: str,
    agent_version_id: str,
) -> CallLifecycle | NullLifecycle:
    try:
        return CallLifecycle(
            publisher,
            tenant_id=UUID(tenant_id),
            call_id=UUID(call_id),
            agent_id=UUID(agent_id),
            agent_version_id=UUID(agent_version_id),
        )
    except ValueError:
        logger.exception("call lifecycle ids are not uuids")
        return NullLifecycle()


_shared: LifecyclePublisher | None = None


def shared_publisher() -> LifecyclePublisher:
    global _shared
    if _shared is None:
        _shared = LifecyclePublisher.from_env()
    return _shared


def _ms(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return max(0, int(value))
