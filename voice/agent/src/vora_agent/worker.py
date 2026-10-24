"""LiveKit worker. Sarvam does STT, the conversation LLM, and TTS."""

import asyncio
import json
import logging
import os
import time
import urllib.request
from collections.abc import Callable
from typing import Any

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RunContext,
    TurnHandlingOptions,
    WorkerOptions,
    cli,
    function_tool,
    get_job_context,
)
from livekit.agents.metrics import EOUMetrics, LLMMetrics, TTSMetrics
from livekit.plugins import sarvam, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from vora_agent.call_start import StartedCall, start_call
from vora_agent.lifecycle import open_call_lifecycle, shared_publisher, sip_call_status
from vora_agent.metrics import TurnTracker, turn_emf
from vora_agent.pacing import install_sarvam_pacing
from vora_agent.sarvam_credentials import SarvamRuntime, load_sarvam_runtime
from vora_agent.voice_plan import VoicePlan, voice_plan

logger = logging.getLogger("vora.agent")


def _post(url: str, *, json: dict[str, str], headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json_dumps(json),
        headers={**headers, "content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        body = json.loads(response.read().decode())
    if not isinstance(body, dict):
        raise ValueError("call start returned a non-object")
    return body


def json_dumps(payload: dict[str, str]) -> bytes:
    return json.dumps(payload).encode()


class Receptionist(Agent):
    def __init__(self, instructions: str, *, on_end: Callable[[], None] | None = None) -> None:
        super().__init__(instructions=instructions)
        self._on_end = on_end

    @function_tool
    async def end_call(self, ctx: RunContext) -> str:
        """End the call when the caller is done talking."""
        if self._on_end is not None:
            self._on_end()
        await ctx.wait_for_playout()
        await get_job_context().delete_room()
        return "ended"


def _get(url: str, *, headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=10) as response:
        body = json.loads(response.read().decode())
    if not isinstance(body, dict):
        raise ValueError("sarvam settings returned a non-object")
    return body


def _session(plan: VoicePlan, api_key: str) -> AgentSession:
    return AgentSession(
        vad=silero.VAD.load(),
        stt=sarvam.STT(
            language=plan.stt_language,
            model=plan.stt_model,
            mode=plan.stt_mode,
            api_key=api_key,
        ),
        llm=sarvam.LLM(model=plan.llm_model, api_key=api_key),
        tts=sarvam.TTS(
            target_language_code=plan.tts_language,
            model=plan.tts_model,
            speaker=plan.tts_speaker,
            api_key=api_key,
        ),
        turn_handling=TurnHandlingOptions(
            turn_detection=MultilingualModel(),
            interruption={"enabled": True, "mode": "vad"},
        ),
    )


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload), flush=True)


async def _publish(room: rtc.Room, payload: dict[str, object]) -> None:
    try:
        await room.local_participant.publish_data(
            json.dumps(payload).encode(),
            topic="vora.turn",
            reliable=True,
        )
    except Exception:
        logger.exception("turn metric publish failed")


async def entrypoint(ctx: JobContext) -> None:
    install_sarvam_pacing()
    await ctx.connect()
    try:
        metadata = json.loads(ctx.room.metadata or "{}")
    except json.JSONDecodeError:
        metadata = {}
    if not isinstance(metadata, dict) or "tenant_id" not in metadata or "agent_id" not in metadata:
        logger.info("room has no agent metadata; leaving")
        return

    tenant_id = str(metadata["tenant_id"])
    agent_id = str(metadata["agent_id"])
    runtime = await asyncio.to_thread(
        load_sarvam_runtime,
        os.environ.get("VORA_API_INTERNAL_URL", ""),
        os.environ.get("INTERNAL_AUTH_SECRET", ""),
        env_key=os.environ.get("SARVAM_API_KEY", ""),
        get=_get,
    )
    if not runtime.api_key:
        logger.error("sarvam_key_missing")
        return
    logger.info("sarvam_key_loaded source=%s", runtime.source)
    started = await asyncio.to_thread(
        start_call,
        os.environ["VORA_API_INTERNAL_URL"],
        os.environ["INTERNAL_AUTH_SECRET"],
        {"tenant_id": tenant_id, "agent_id": agent_id},
        post=_post,
    )
    await _run_call(ctx, started, runtime, tenant_id=tenant_id, agent_id=agent_id)


def _guard(fn: Callable[..., None]) -> Callable[..., None]:
    def wrapped(*args: object, **kwargs: object) -> None:
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("lifecycle listener failed")

    return wrapped


async def _run_call(
    ctx: JobContext,
    started: StartedCall,
    runtime: SarvamRuntime,
    *,
    tenant_id: str,
    agent_id: str,
) -> None:
    plan = voice_plan(
        started.config,
        stt_model=runtime.stt_model,
        tts_model=runtime.tts_model,
        llm_model=runtime.llm_model,
    )
    session = _session(plan, runtime.api_key)
    tracker = TurnTracker()
    lifecycle = open_call_lifecycle(
        shared_publisher(),
        tenant_id=tenant_id,
        call_id=started.call_id,
        agent_id=agent_id,
        agent_version_id=started.agent_version_id,
    )
    reason = {"value": "disconnected"}
    tasks: list[asyncio.Task[None]] = []
    lock = asyncio.Lock()

    async def step(fn: Callable[[], None]) -> None:
        async with lock:
            await asyncio.to_thread(fn)

    def spawn(fn: Callable[[], None]) -> None:
        tasks.append(asyncio.create_task(step(fn)))

    async def finish(shutdown_reason: str = "") -> None:
        try:
            while True:
                pending = [task for task in tasks if not task.done()]
                if not pending:
                    break
                await asyncio.gather(*pending, return_exceptions=True)
            if reason["value"] == "disconnected" and shutdown_reason.strip():
                reason["value"] = shutdown_reason.strip()
            await step(lambda: lifecycle.ended(reason["value"]))
        except Exception:
            logger.exception("call.ended publish failed")

    def scan() -> None:
        remote = getattr(ctx.room, "remote_participants", {}) or {}
        for participant in remote.values():
            lifecycle.observe_sip_status(sip_call_status(getattr(participant, "attributes", None)))

    def ready() -> None:
        scan()
        lifecycle.session_ready()

    ctx.add_shutdown_callback(finish)
    await step(lifecycle.created)
    await step(scan)

    def on_participant(participant: object, *_rest: object) -> None:
        status = sip_call_status(getattr(participant, "attributes", None))
        if status:
            spawn(lambda status=status: lifecycle.observe_sip_status(status))

    def on_attributes(*args: object) -> None:
        participant = args[-1] if args else None
        on_participant(participant)

    def on_disconnected(participant: object, *_rest: object) -> None:
        local = getattr(ctx.room, "local_participant", None)
        if participant is local:
            return
        local_id = getattr(local, "identity", None)
        if local_id is not None and getattr(participant, "identity", None) == local_id:
            return
        if reason["value"] == "disconnected":
            reason["value"] = "caller_hangup"

    def on_close(*args: object) -> None:
        if reason["value"] != "disconnected":
            return
        event = args[0] if args else None
        close_name = getattr(getattr(event, "reason", None), "name", "")
        if getattr(event, "error", None) is not None or close_name == "ERROR":
            reason["value"] = "error"
        elif close_name == "PARTICIPANT_DISCONNECTED":
            reason["value"] = "caller_hangup"
        elif close_name == "USER_INITIATED":
            reason["value"] = "agent_ended"

    ctx.room.on("participant_connected", _guard(on_participant))
    ctx.room.on("participant_attributes_changed", _guard(on_attributes))
    ctx.room.on("participant_disconnected", _guard(on_disconnected))

    def _on_metrics(event: object) -> None:
        metric = getattr(event, "metrics", event)
        if not isinstance(metric, (EOUMetrics, LLMMetrics, TTSMetrics)):
            return
        folded = tracker.observe(metric)
        if folded is None:
            return
        payload = turn_emf(
            tenant_id=tenant_id,
            agent_id=agent_id,
            agent_version_id=started.agent_version_id,
            call_id=started.call_id,
            now_ms=int(time.time() * 1000),
            **folded,
        )
        _emit(payload)
        asyncio.create_task(_publish(ctx.room, payload))
        speech_id = str(getattr(metric, "speech_id", None) or "turn")
        spawn(lambda: lifecycle.complete_speech(speech_id, folded))

    session.on("metrics_collected", _on_metrics)
    session.on("close", _guard(on_close))

    def agent_ended() -> None:
        reason["value"] = "agent_ended"

    await session.start(agent=Receptionist(plan.prompt, on_end=agent_ended), room=ctx.room)
    await step(ready)
    await session.say(plan.greeting, allow_interruptions=plan.barge_in)


def main() -> None:
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()
