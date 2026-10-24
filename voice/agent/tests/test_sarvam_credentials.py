from vora_agent.sarvam_credentials import load_sarvam_runtime, runtime_from


def test_settings_key_wins_over_the_environment() -> None:
    runtime = runtime_from(
        {
            "api_key": "from-settings-1234",
            "source": "settings",
            "stt_model": "saaras:v4",
            "tts_model": "bulbul:v3",
            "llm_model": "sarvam-30b",
        },
        env_key="env-key-9999",
    )
    assert runtime.api_key == "from-settings-1234"
    assert runtime.source == "settings"
    assert runtime.llm_model == "sarvam-30b"
    assert runtime.stt_model == "saaras:v4"


def test_empty_setting_falls_back_to_the_environment() -> None:
    runtime = runtime_from({"api_key": "", "source": "missing"}, env_key="env-key-9999")
    assert runtime.api_key == "env-key-9999"
    assert runtime.source == "env"
    assert runtime.llm_model == "sarvam-105b-conversations"


def test_public_api_and_a_failed_read_use_the_environment() -> None:
    def get(url: str, *, headers: dict[str, str]) -> dict[str, object]:
        raise AssertionError(url)

    public = load_sarvam_runtime(
        "https://playground-dev.hellovora.ai",
        "secret",
        env_key="env-key-9999",
        get=get,
    )
    assert public.api_key == "env-key-9999"
    assert public.source == "env"

    def fail(url: str, *, headers: dict[str, str]) -> dict[str, object]:
        raise TimeoutError(url)

    failed = load_sarvam_runtime(
        "http://api.vora2.local:8000",
        "secret",
        env_key="env-key-9999",
        get=fail,
    )
    assert failed.source == "env"
    assert failed.api_key == "env-key-9999"


def test_private_api_payload_is_used() -> None:
    seen: dict[str, object] = {}

    def get(url: str, *, headers: dict[str, str]) -> dict[str, object]:
        seen["url"] = url
        seen["headers"] = headers
        return {"api_key": "from-settings-1234", "source": "settings"}

    runtime = load_sarvam_runtime(
        "http://api.vora2.local:8000",
        "service-secret",
        env_key="env-key-9999",
        get=get,
    )
    assert seen["url"] == "http://api.vora2.local:8000/internal/integrations/sarvam"
    assert seen["headers"] == {"x-vora-internal": "service-secret"}
    assert runtime.api_key == "from-settings-1234"
    assert runtime.source == "settings"
