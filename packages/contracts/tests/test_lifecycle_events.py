import pytest
from pydantic import ValidationError

from contracts import (
    CallAnswered,
    CallCreated,
    CallEnded,
    CallRinging,
    TurnCompleted,
    parse_lifecycle_event,
)

_TENANT = "11111111-1111-1111-1111-111111111111"
_CALL = "22222222-2222-2222-2222-222222222222"
_AGENT = "33333333-3333-3333-3333-333333333333"
_VERSION = "44444444-4444-4444-4444-444444444444"
_AT = "2026-10-24T12:00:00+05:30"


def _base() -> dict[str, str]:
    return {"tenant_id": _TENANT, "call_id": _CALL, "occurred_at": _AT}


def _round_trip(model: type, raw: dict) -> None:
    parsed = model.model_validate(raw)
    again = model.model_validate_json(parsed.model_dump_json())
    assert again == parsed
    assert parse_lifecycle_event(parsed.model_dump_json()) == parsed


def test_call_created_round_trips_json() -> None:
    _round_trip(
        CallCreated,
        {
            **_base(),
            "event": "call.created",
            "agent_id": _AGENT,
            "agent_version_id": _VERSION,
        },
    )


def test_call_ringing_round_trips_json() -> None:
    _round_trip(CallRinging, {**_base(), "event": "call.ringing"})


def test_call_answered_round_trips_json() -> None:
    _round_trip(CallAnswered, {**_base(), "event": "call.answered"})


def test_turn_completed_round_trips_json() -> None:
    _round_trip(
        TurnCompleted,
        {
            **_base(),
            "event": "turn.completed",
            "turn_index": 0,
            "stt_ms": 120,
            "llm_ms": 340,
            "tts_ms": 210,
            "ttfw_ms": 670,
        },
    )


def test_call_ended_round_trips_json() -> None:
    _round_trip(
        CallEnded,
        {
            **_base(),
            "event": "call.ended",
            "reason": "caller_hangup",
            "duration_ms": 12500,
            "recording_key": (
                "tenants/11111111-1111-1111-1111-111111111111/calls/22222222/audio.ogg"
            ),
        },
    )


def test_call_ended_allows_missing_recording_key() -> None:
    raw = {**_base(), "event": "call.ended", "reason": "error", "duration_ms": 0}
    parsed = CallEnded.model_validate(raw)
    again = CallEnded.model_validate_json(parsed.model_dump_json())
    assert again == parsed
    assert again.recording_key is None


def test_turn_rejects_negative_latency() -> None:
    raw = {
        **_base(),
        "event": "turn.completed",
        "turn_index": 1,
        "stt_ms": -1,
        "llm_ms": 0,
        "tts_ms": 0,
        "ttfw_ms": 0,
    }
    with pytest.raises(ValidationError):
        TurnCompleted.model_validate(raw)


def test_unknown_event_is_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_lifecycle_event({**_base(), "event": "call.transcript"})
