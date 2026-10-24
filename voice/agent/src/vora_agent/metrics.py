def turn_emf(
    *,
    tenant_id: str,
    agent_id: str,
    agent_version_id: str,
    call_id: str,
    eos_to_stt_final: int,
    llm_first_token: int,
    tts_first_byte: int,
    time_to_first_word: int,
    now_ms: int,
) -> dict[str, object]:
    """One CloudWatch EMF line for a turn. The dashboard is a later ticket."""
    names = (
        "eos_to_stt_final",
        "llm_first_token",
        "tts_first_byte",
        "time_to_first_word",
    )
    return {
        "_aws": {
            "Timestamp": now_ms,
            "CloudWatchMetrics": [
                {
                    "Namespace": "Vora/Voice",
                    "Dimensions": [["tenant_id", "agent_id", "agent_version_id", "call_id"]],
                    "Metrics": [{"Name": name, "Unit": "Milliseconds"} for name in names],
                }
            ],
        },
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "agent_version_id": agent_version_id,
        "call_id": call_id,
        "eos_to_stt_final": eos_to_stt_final,
        "llm_first_token": llm_first_token,
        "tts_first_byte": tts_first_byte,
        "time_to_first_word": time_to_first_word,
    }


class TurnTracker:
    """Fold LiveKit's per-stage metrics into one EMF payload when TTS audio starts."""

    def __init__(self) -> None:
        self._turns: dict[str, dict[str, int]] = {}

    def observe(self, metric: object) -> dict[str, int] | None:
        speech_id = str(getattr(metric, "speech_id", None) or "turn")
        row = self._turns.setdefault(speech_id, {})
        kind = str(getattr(metric, "type", ""))
        if kind == "eou_metrics":
            row["eos_to_stt_final"] = _ms(getattr(metric, "transcription_delay", 0))
        elif kind == "llm_metrics" and not getattr(metric, "cancelled", False):
            row["llm_first_token"] = _ms(getattr(metric, "ttft", 0))
        elif kind == "tts_metrics" and not getattr(metric, "cancelled", False):
            row["tts_first_byte"] = _ms(getattr(metric, "ttfb", 0))
        if "tts_first_byte" not in row:
            return None
        eos = row.get("eos_to_stt_final", 0)
        llm = row.get("llm_first_token", 0)
        tts = row["tts_first_byte"]
        return {
            "eos_to_stt_final": eos,
            "llm_first_token": llm,
            "tts_first_byte": tts,
            "time_to_first_word": eos + llm + tts,
        }


def _ms(seconds: object) -> int:
    return int(float(seconds) * 1000)
