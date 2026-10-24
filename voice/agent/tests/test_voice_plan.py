from vora_agent.config import load_agent_config
from vora_agent.voice_plan import voice_plan


def test_voice_plan_uses_saaras_bulbul_and_speaks_the_greeting_first() -> None:
    config = load_agent_config(
        {
            "prompt": "Qualify the site visit.",
            "greeting": "Namaste! Main Vora hoon.",
            "language": "hi-IN",
            "languages": ["hi-IN", "en-IN"],
            "voice": "anushka",
            "llm": {"provider": "sarvam"},
        }
    )
    plan = voice_plan(config)
    assert plan.stt_model == "saaras:v4"
    assert plan.stt_mode == "codemix"
    assert plan.stt_language == "hi-IN"
    assert plan.tts_model == "bulbul:v3"
    assert plan.tts_speaker == "anushka"
    assert plan.tts_language == "hi-IN"
    assert plan.llm_model == "sarvam-105b-conversations"
    assert plan.greeting == "Namaste! Main Vora hoon."
    assert plan.vad == "silero"
    assert plan.turn_detection == "livekit-multilingual"
    assert plan.barge_in is True
    assert "end_call" in plan.tools
    custom = voice_plan(
        config, llm_model="sarvam-30b", stt_model="saaras:v3", tts_model="bulbul:v2"
    )
    assert custom.llm_model == "sarvam-30b"
    assert custom.stt_model == "saaras:v3"
    assert custom.tts_model == "bulbul:v2"
