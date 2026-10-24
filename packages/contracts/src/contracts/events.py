from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter


class _Event(BaseModel):
    """One call-lifecycle fact. Publishers and consumers share this shape."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    call_id: UUID
    occurred_at: AwareDatetime


class CallCreated(_Event):
    event: Literal["call.created"] = "call.created"
    agent_id: UUID
    agent_version_id: UUID


class CallRinging(_Event):
    event: Literal["call.ringing"] = "call.ringing"


class CallAnswered(_Event):
    event: Literal["call.answered"] = "call.answered"


class TurnCompleted(_Event):
    event: Literal["turn.completed"] = "turn.completed"
    turn_index: int = Field(ge=0)
    stt_ms: int = Field(ge=0)
    llm_ms: int = Field(ge=0)
    tts_ms: int = Field(ge=0)
    ttfw_ms: int = Field(ge=0)


class CallEnded(_Event):
    """`duration_ms` is the call duration. `recording_key` is null until egress writes one."""

    event: Literal["call.ended"] = "call.ended"
    reason: str = Field(min_length=1)
    duration_ms: int = Field(ge=0)
    recording_key: str | None = None


LifecycleEvent = Annotated[
    CallCreated | CallRinging | CallAnswered | TurnCompleted | CallEnded,
    Field(discriminator="event"),
]

_ADAPTER = TypeAdapter(LifecycleEvent)


def parse_lifecycle_event(payload: dict[str, object] | str | bytes) -> LifecycleEvent:
    if isinstance(payload, (str, bytes)):
        return _ADAPTER.validate_json(payload)
    return _ADAPTER.validate_python(payload)
