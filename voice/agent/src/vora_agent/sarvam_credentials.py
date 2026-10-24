"""Load the Sarvam key at call time.

Global Settings is the source. SARVAM_API_KEY is used only when that setting
is empty or the private API cannot be reached.
"""

from collections.abc import Callable

from vora_agent.call_start import PublicApiRejected, require_private_base
from vora_agent.voice_plan import BULBUL, SAARAS, SARVAM_LLM


class SarvamRuntime:
    def __init__(
        self, *, api_key: str, stt_model: str, tts_model: str, llm_model: str, source: str
    ) -> None:
        self.api_key = api_key
        self.stt_model = stt_model
        self.tts_model = tts_model
        self.llm_model = llm_model
        self.source = source


def runtime_from(payload: dict[str, object] | None, *, env_key: str) -> SarvamRuntime:
    api_key = ""
    stt_model = SAARAS
    tts_model = BULBUL
    llm_model = SARVAM_LLM
    source = "missing"
    if payload:
        api_key = str(payload.get("api_key") or "").strip()
        stt_model = str(payload.get("stt_model") or stt_model).strip() or stt_model
        tts_model = str(payload.get("tts_model") or tts_model).strip() or tts_model
        llm_model = str(payload.get("llm_model") or llm_model).strip() or llm_model
        named = str(payload.get("source") or "settings")
        source = named if api_key and named in {"settings", "env"} else "missing"
    if not api_key:
        api_key = env_key.strip()
        source = "env" if api_key else "missing"
    return SarvamRuntime(
        api_key=api_key,
        stt_model=stt_model,
        tts_model=tts_model,
        llm_model=llm_model,
        source=source,
    )


def load_sarvam_runtime(
    base_url: str,
    secret: str,
    *,
    env_key: str,
    get: Callable[..., dict[str, object]],
) -> SarvamRuntime:
    payload: dict[str, object] | None = None
    if base_url.strip():
        try:
            root = require_private_base(base_url)
            body = get(
                f"{root}/internal/integrations/sarvam",
                headers={"x-vora-internal": secret},
            )
            payload = body if isinstance(body, dict) else None
        except (PublicApiRejected, OSError, ValueError, TimeoutError):
            payload = None
    return runtime_from(payload, env_key=env_key)
