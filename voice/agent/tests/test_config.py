import pytest

from vora_agent.config import UnsupportedLlmProvider, load_agent_config


def _raw() -> dict[str, object]:
    return {
        "prompt": "You are a demo receptionist.",
        "greeting": "Namaste! Main Vora hoon.",
        "language": "hi-IN",
        "languages": ["hi-IN", "en-IN"],
        "voice": "anushka",
        "tools": ["end_call"],
        "llm": {"provider": "sarvam"},
    }


def test_loads_sarvam_code_mix_config() -> None:
    config = load_agent_config(_raw())
    assert config.greeting == "Namaste! Main Vora hoon."
    assert config.prompt.startswith("You are")
    assert config.language == "hi-IN"
    assert config.languages == ("hi-IN", "en-IN")
    assert config.voice == "anushka"
    assert config.llm_provider == "sarvam"
    assert config.code_mix is True


def test_accepts_flat_llm_provider_and_short_language_codes() -> None:
    raw = _raw()
    del raw["llm"]
    raw["llm_provider"] = "sarvam"
    raw["language"] = "hi"
    raw["languages"] = ["hi", "en"]
    config = load_agent_config(raw)
    assert config.llm_provider == "sarvam"
    assert config.language == "hi-IN"
    assert config.languages == ("hi-IN", "en-IN")
    assert config.code_mix is True


def test_rejects_a_non_sarvam_provider() -> None:
    raw = _raw()
    raw["llm"] = {"provider": "openai"}
    with pytest.raises(UnsupportedLlmProvider):
        load_agent_config(raw)


def test_single_language_is_not_code_mix() -> None:
    raw = _raw()
    raw["languages"] = ["en-IN"]
    raw["language"] = "en-IN"
    config = load_agent_config(raw)
    assert config.language == "en-IN"
    assert config.languages == ("en-IN",)
    assert config.code_mix is False
