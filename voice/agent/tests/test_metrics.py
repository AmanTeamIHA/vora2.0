from vora_agent.metrics import turn_emf


def test_turn_emf_shape() -> None:
    payload = turn_emf(
        tenant_id="ten",
        agent_id="agt",
        agent_version_id="ver",
        call_id="call",
        eos_to_stt_final=120,
        llm_first_token=340,
        tts_first_byte=80,
        time_to_first_word=540,
        now_ms=1_700_000_000_000,
    )
    aws = payload["_aws"]
    metrics = aws["CloudWatchMetrics"][0]
    names = [item["Name"] for item in metrics["Metrics"]]
    assert aws["Timestamp"] == 1_700_000_000_000
    assert metrics["Namespace"] == "Vora/Voice"
    assert metrics["Dimensions"] == [["tenant_id", "agent_id", "agent_version_id", "call_id"]]
    assert names == [
        "eos_to_stt_final",
        "llm_first_token",
        "tts_first_byte",
        "time_to_first_word",
    ]
    assert {item["Unit"] for item in metrics["Metrics"]} == {"Milliseconds"}
    assert payload["tenant_id"] == "ten"
    assert payload["agent_id"] == "agt"
    assert payload["agent_version_id"] == "ver"
    assert payload["call_id"] == "call"
    assert payload["eos_to_stt_final"] == 120
    assert payload["llm_first_token"] == 340
    assert payload["tts_first_byte"] == 80
    assert payload["time_to_first_word"] == 540
