"""Redis Streams consumer group on the shared call-lifecycle stream."""

import logging
import os
import socket
from collections.abc import Mapping
from dataclasses import dataclass

from contracts import CALLS_EVENTS_STREAM
from redis.exceptions import ResponseError

logger = logging.getLogger(__name__)

CALL_EVENTS_GROUP = "vora-api-calls"


@dataclass(frozen=True)
class StreamEntry:
    message_id: str
    fields: dict[str, str]


class RedisEventStream:
    """One consumer in CALL_EVENTS_GROUP. Pending entries are claimed after 60s."""

    def __init__(
        self,
        client: object,
        *,
        group: str = CALL_EVENTS_GROUP,
        consumer: str | None = None,
        stream: str = CALLS_EVENTS_STREAM,
    ) -> None:
        self._redis = client
        self.group = group
        self.consumer = consumer or f"{socket.gethostname()}-{os.getpid()}"
        self.stream = stream

    def ensure_group(self) -> None:
        try:
            self._redis.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def read_pending(self, *, count: int) -> list[StreamEntry]:
        try:
            self._redis.xautoclaim(
                self.stream,
                self.group,
                self.consumer,
                60_000,
                start_id="0-0",
                count=count,
            )
        except ResponseError as exc:
            logger.warning("call lifecycle xautoclaim skipped: %s", exc)
        return _entries(
            self._redis.xreadgroup(
                self.group,
                self.consumer,
                {self.stream: "0"},
                count=count,
            )
        )

    def read_new(self, *, count: int, block_ms: int | None) -> list[StreamEntry]:
        kwargs: dict[str, int] = {"count": count}
        if block_ms is not None:
            kwargs["block"] = block_ms
        return _entries(
            self._redis.xreadgroup(
                self.group,
                self.consumer,
                {self.stream: ">"},
                **kwargs,
            )
        )

    def ack(self, message_id: str) -> None:
        self._redis.xack(self.stream, self.group, message_id)


def _entries(raw: object) -> list[StreamEntry]:
    if not raw:
        return []
    found: list[StreamEntry] = []
    for _stream_name, messages in raw:  # type: ignore[misc]
        for message_id, fields in messages:
            found.append(StreamEntry(_text(message_id), _field_map(fields)))
    return found


def _field_map(fields: Mapping[object, object]) -> dict[str, str]:
    return {_text(key): _text(value) for key, value in fields.items()}


def _text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value)
