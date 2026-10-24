import io
import json
import sys

import pytest

from vora_agent.latency_report import EmfParseError, main, nearest_rank, parse_emf_text, summarize
from vora_agent.metrics import turn_emf

# Ten turns. Time to first word is not recomputed from the stages, so a line
# whose sum disagrees with time_to_first_word still reports the printed value.
_TURNS = (
    (80, 200, 70, 400),
    (90, 250, 80, 510),
    (100, 300, 90, 600),
    (110, 320, 100, 690),
    (120, 340, 110, 720),
    (130, 360, 120, 800),
    (150, 400, 140, 860),
    (180, 450, 160, 910),
    (220, 500, 200, 1100),
    (400, 700, 300, 1500),
)


def _line(stt: int, llm: int, tts: int, ttfw: int, *, call_id: str = "call-1") -> str:
    return json.dumps(
        turn_emf(
            tenant_id="ten",
            agent_id="agt",
            agent_version_id="ver",
            call_id=call_id,
            eos_to_stt_final=stt,
            llm_first_token=llm,
            tts_first_byte=tts,
            time_to_first_word=ttfw,
            now_ms=1_700_000_000_000,
        )
    )


def _log() -> str:
    lines = ["worker ready", "INFO not json {broken"]
    lines.extend(
        _line(*turn, call_id=f"call-{index}") for index, turn in enumerate(_TURNS, start=1)
    )
    lines.append(json.dumps({"event": "call.ended", "ttfw_ms": 1, "stt_ms": 1}))
    return "\n".join(lines)


def test_nearest_rank_picks_a_sample() -> None:
    values = [400, 510, 600, 690, 720, 800, 860, 910, 1100, 1500]
    assert nearest_rank(values, 50) == 720
    assert nearest_rank(values, 95) == 1500
    assert nearest_rank([10, 30], 50) == 10
    assert nearest_rank([10, 30], 95) == 30
    assert nearest_rank([42], 50) == 42
    assert nearest_rank([42], 95) == 42


def test_percentiles_match_emf_lines() -> None:
    report = summarize(parse_emf_text(_log()))
    assert report["n"] == 10
    assert report["method"] == "nearest-rank"
    assert report["tts_only"] == 0
    assert report["p50"] == {"ttfw_ms": 720, "stt_ms": 120, "llm_ms": 340, "tts_ms": 110}
    assert report["p95"] == {"ttfw_ms": 1500, "stt_ms": 400, "llm_ms": 700, "tts_ms": 300}
    turns = report["turns"]
    assert turns[0]["call_id"] == "call-1"
    assert turns[0]["timestamp_ms"] == 1_700_000_000_000
    assert turns[4]["ttfw_ms"] == 720
    assert turns[4]["ttfw_ms"] != turns[4]["stt_ms"] + turns[4]["llm_ms"] + turns[4]["tts_ms"]


def test_prefixed_line_and_log_event_wrapper() -> None:
    line = _line(120, 340, 80, 540)
    prefixed = parse_emf_text(f"2026-10-24T22:00:00Z {line}")
    wrapped = parse_emf_text(json.dumps({"events": [{"message": line + "\n", "timestamp": 5}]}))
    assert prefixed[0].ttfw_ms == 540
    assert wrapped[0].stt_ms == 120
    assert wrapped[0].llm_ms == 340
    assert wrapped[0].tts_ms == 80


def test_greeting_turn_is_counted_and_included() -> None:
    text = "\n".join((_line(0, 0, 80, 80), _line(100, 200, 50, 350)))
    report = summarize(parse_emf_text(text))
    assert report["n"] == 2
    assert report["tts_only"] == 1
    assert report["p50"]["ttfw_ms"] == 80
    assert report["p95"]["ttfw_ms"] == 350


def test_empty_input_is_an_error() -> None:
    assert parse_emf_text("nothing to see\n") == []
    with pytest.raises(ValueError, match="no vora.turn"):
        summarize([])


def test_incomplete_vora_voice_line_is_an_error() -> None:
    payload = json.loads(_line(1, 2, 3, 6))
    del payload["tts_first_byte"]
    with pytest.raises(EmfParseError, match="line 1: missing tts_first_byte"):
        parse_emf_text(json.dumps(payload))


def test_negative_and_boolean_metrics_are_rejected() -> None:
    negative = json.loads(_line(1, 2, 3, 6))
    negative["llm_first_token"] = -1
    flagged = json.loads(_line(1, 2, 3, 6))
    flagged["eos_to_stt_final"] = True
    with pytest.raises(EmfParseError, match="negative"):
        parse_emf_text(json.dumps(negative))
    with pytest.raises(EmfParseError, match="not a number"):
        parse_emf_text(json.dumps(flagged))


def test_cli_prints_the_report(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "emf.log"
    path.write_text(_line(120, 340, 80, 540) + "\n")
    assert main([str(path)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["n"] == 1
    assert report["p50"]["ttfw_ms"] == 540
    assert report["p95"]["tts_ms"] == 80


def test_cli_rejects_empty_stdin(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    assert main([]) == 2
    assert "no vora.turn" in capsys.readouterr().err
