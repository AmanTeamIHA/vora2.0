from dataclasses import dataclass

from vora_agent.config import AgentConfig, UnsupportedLlmProvider

SARVAM_LLM = "sarvam-105b-conversations"
SAARAS = "saaras:v4"
BULBUL = "bulbul:v3"


@dataclass(frozen=True)
class VoicePlan:
    stt_model: str
    stt_mode: str
    stt_language: str
    tts_model: str
    tts_speaker: str
    tts_language: str
    llm_model: str
    greeting: str
    prompt: str
    vad: str
    turn_detection: str
    barge_in: bool
    tools: tuple[str, ...]


def voice_plan(config: AgentConfig) -> VoicePlan:
    if config.llm_provider != "sarvam":
        raise UnsupportedLlmProvider(config.llm_provider)
    tools = tuple(dict.fromkeys((*config.tools, "end_call")))
    return VoicePlan(
        stt_model=SAARAS,
        stt_mode="codemix" if config.code_mix else "transcribe",
        stt_language=config.language,
        tts_model=BULBUL,
        tts_speaker=config.voice,
        tts_language=config.language,
        llm_model=SARVAM_LLM,
        greeting=config.greeting,
        prompt=config.prompt,
        vad="silero",
        turn_detection="livekit-multilingual",
        barge_in=True,
        tools=tools,
    )
