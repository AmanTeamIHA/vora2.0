import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from contracts import CALLS_EVENTS_STREAM, parse_lifecycle_event, tenant_calls_stream

from vora_agent.lifecycle import (
    CallLifecycle,
    LifecyclePublisher,
    open_call_lifecycle,
    sip_call_status,
)
from vora_agent.metrics import TurnTracker

_TENANT = UUID("11111111-1111-1111-1111-111111111111")
_CALL = UUID("22222222-2222-2222-2222-222222222222")
_AGENT = UUID("33333333-3333-3333-3333-333333333333")
_VERSION = UUID("44444444-4444-4444-4444-444444444444")


class Clock:
    def __init__(self) -> None:
        self.mono_s = 100.0
        self.when = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)

    def mono(self) -> float:
        return self.mono_s

    def now(self) -> datetime:
        return self.when

    def advance(self, seconds: float) -> None:
        self.mono_s += seconds
        self.when += timedelta(seconds=seconds)


class FakeRedis:
    def __init__(self) -> None:
        self.streams: dict[str, list[str]] = {}

    def xadd(self, name: str, fields: dict[str, str]) -> str:
        self.streams.setdefault(name, []).append(fields["body"])
        return "1-0"

    def bodies(self, name: str) -> list[str]:
        return list(self.streams.get(name, []))


class BoomRedis:
    def __init__(self) -> None:
        self.calls = 0

    def xadd(self, name: str, fields: dict[str, str]) -> str:
        self.calls += 1
        raise ConnectionError("redis down")


class _Metric:
    def __init__(self, kind: str, speech_id: str, **values: float) -> None:
        self.type = kind
        self.speech_id = speech_id
        self.cancelled = False
        for name, value in values.items():
            setattr(self, name, value)


def _life(redis: FakeRedis | BoomRedis | None, clock: Clock | None = None) -> CallLifecycle:
    source = clock or Clock()
    return CallLifecycle(
        LifecyclePublisher(redis),
        tenant_id=_TENANT,
        call_id=_CALL,
        agent_id=_AGENT,
        agent_version_id=_VERSION,
        now=source.now,
        monotonic=source.mono,
    )


def _names(redis: FakeRedis) -> list[str]:
    return [parse_lifecycle_event(body).event for body in redis.bodies(CALLS_EVENTS_STREAM)]


def test_full_call_publishes_ordered_events_to_both_streams() -> None:
    redis = FakeRedis()
    clock = Clock()
    life = _life(redis, clock)
    life.created()
    life.observe_sip_status("ringing")
    life.observe_sip_status("ringing")
    life.observe_sip_status("active")
    life.complete_speech("s1", _folded(120, 340, 80, 540))
    life.complete_speech("s1", _folded(1, 1, 1, 3))
    life.complete_speech("s2", _folded(10, 20, 30, 60))
    clock.advance(2.5)
    life.ended("caller_hangup")
    life.ended("disconnected")

    global_bodies = redis.bodies(CALLS_EVENTS_STREAM)
    tenant_bodies = redis.bodies(tenant_calls_stream(_TENANT))
    assert global_bodies == tenant_bodies
    parsed = [parse_lifecycle_event(body) for body in global_bodies]
    assert [event.event for event in parsed] == [
        "call.created",
        "call.ringing",
        "call.answered",
        "turn.completed",
        "turn.completed",
        "call.ended",
    ]
    created = parsed[0]
    assert created.event == "call.created"
    assert created.tenant_id == _TENANT
    assert created.call_id == _CALL
    assert created.agent_id == _AGENT
    assert created.agent_version_id == _VERSION
    first = parsed[3]
    assert first.event == "turn.completed"
    assert first.turn_index == 0
    assert first.stt_ms == 120
    assert first.llm_ms == 340
    assert first.tts_ms == 80
    assert first.ttfw_ms == 540
    second = parsed[4]
    assert second.event == "turn.completed"
    assert second.turn_index == 1
    assert second.stt_ms == 10
    ended = parsed[5]
    assert ended.event == "call.ended"
    assert ended.reason == "caller_hangup"
    assert ended.duration_ms == 2500
    assert ended.recording_key is None


def test_browser_call_skips_ringing() -> None:
    redis = FakeRedis()
    life = _life(redis)
    life.created()
    life.session_ready()
    life.complete_speech("greeting", _folded(0, 0, 40, 40))
    life.ended("disconnected")
    assert _names(redis) == [
        "call.created",
        "call.answered",
        "turn.completed",
        "call.ended",
    ]
    assert redis.bodies(CALLS_EVENTS_STREAM) == redis.bodies(tenant_calls_stream(_TENANT))


def test_tracker_fold_maps_onto_turn_completed() -> None:
    tracker = TurnTracker()
    speech = "speech-1"
    assert tracker.observe(_Metric("eou_metrics", speech, transcription_delay=0.125)) is None
    assert tracker.observe(_Metric("llm_metrics", speech, ttft=0.25)) is None
    folded = tracker.observe(_Metric("tts_metrics", speech, ttfb=0.5))
    assert folded is not None

    redis = FakeRedis()
    life = _life(redis)
    life.created()
    life.session_ready()
    life.complete_speech(speech, folded)
    life.ended("disconnected")
    parsed = [parse_lifecycle_event(body) for body in redis.bodies(CALLS_EVENTS_STREAM)]
    turn = parsed[2]
    assert turn.event == "turn.completed"
    assert turn.stt_ms == folded["eos_to_stt_final"]
    assert turn.llm_ms == folded["llm_first_token"]
    assert turn.tts_ms == folded["tts_first_byte"]
    assert turn.ttfw_ms == folded["time_to_first_word"]


def test_turn_during_ringing_is_published_after_answer() -> None:
    redis = FakeRedis()
    life = _life(redis)
    life.created()
    life.observe_sip_status("ringing")
    life.complete_speech("greeting", _folded(0, 0, 15, 15))
    life.session_ready()
    assert _names(redis) == ["call.created", "call.ringing"]
    life.observe_sip_status("active")
    assert _names(redis) == [
        "call.created",
        "call.ringing",
        "call.answered",
        "turn.completed",
    ]


def test_dialing_does_not_emit_ringing() -> None:
    redis = FakeRedis()
    life = _life(redis)
    life.created()
    life.observe_sip_status("dialing")
    life.session_ready()
    assert _names(redis) == ["call.created"]
    life.observe_sip_status("active")
    life.ended("caller_hangup")
    assert _names(redis) == ["call.created", "call.answered", "call.ended"]


def test_redis_error_does_not_raise(caplog: pytest.LogCaptureFixture) -> None:
    redis = BoomRedis()
    life = _life(redis)
    with caplog.at_level(logging.ERROR):
        life.created()
        life.observe_sip_status("ringing")
        life.observe_sip_status("active")
        life.complete_speech("s1", _folded(1, 2, 3, 6))
        life.ended("error")
    assert redis.calls == 10
    assert any("lifecycle publish failed" in record.message for record in caplog.records)


def test_missing_redis_url_does_not_raise(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    with caplog.at_level(logging.WARNING):
        publisher = LifecyclePublisher.from_env()
        life = CallLifecycle(
            publisher,
            tenant_id=_TENANT,
            call_id=_CALL,
            agent_id=_AGENT,
            agent_version_id=_VERSION,
        )
        life.created()
        life.session_ready()
        life.complete_speech("s1", _folded(1, 2, 3, 6))
        life.ended("disconnected")
    assert any("REDIS_URL is not set" in record.message for record in caplog.records)


def test_bad_call_id_skips_lifecycle_without_raising() -> None:
    life = open_call_lifecycle(
        LifecyclePublisher(None),
        tenant_id="not-a-uuid",
        call_id="also-bad",
        agent_id=str(_AGENT),
        agent_version_id=str(_VERSION),
    )
    life.created()
    life.session_ready()
    life.complete_speech("s1", _folded(1, 2, 3, 6))
    life.ended("disconnected")


def test_sip_call_status_reads_the_livekit_attribute() -> None:
    assert sip_call_status({"sip.callStatus": "ringing"}) == "ringing"
    assert sip_call_status({}) == ""
    assert sip_call_status(None) == ""


def _folded(stt: int, llm: int, tts: int, ttfw: int) -> dict[str, int]:
    return {
        "eos_to_stt_final": stt,
        "llm_first_token": llm,
        "tts_first_byte": tts,
        "time_to_first_word": ttfw,
    }
