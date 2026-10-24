"""Nearest-rank p50/p95 from Vora/Voice `vora.turn` EMF lines.

The worker prints one JSON object per spoken turn (`turn_emf`). This report reads
those lines from files or stdin. It does not call Sarvam, LiveKit, or AWS.

    python -m vora_agent.latency_report turns.log

Percentile method is nearest-rank: sort ascending, then take the value at
1-based rank ``ceil(p/100*n)``. p50 and p95 are always one of the measured
samples. Greeting turns, where STT and LLM are both 0, stay in the sample and
are counted in ``tts_only``.
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

WORKER_FIELDS = {
    "time_to_first_word": "ttfw_ms",
    "eos_to_stt_final": "stt_ms",
    "llm_first_token": "llm_ms",
    "tts_first_byte": "tts_ms",
}
REPORT_FIELDS = ("ttfw_ms", "stt_ms", "llm_ms", "tts_ms")
_MAX_DEPTH = 4


class EmfParseError(ValueError):
    """A Vora/Voice line is present but is not a usable turn."""


@dataclass(frozen=True)
class TurnSample:
    ttfw_ms: int
    stt_ms: int
    llm_ms: int
    tts_ms: int
    call_id: str | None = None
    timestamp_ms: int | None = None

    @property
    def tts_only(self) -> bool:
        return self.stt_ms == 0 and self.llm_ms == 0


def nearest_rank(values: Iterable[int], percent: int) -> int:
    """1-based rank ``ceil(percent/100*n)`` on ``values`` sorted ascending."""
    if percent <= 0 or percent > 100:
        raise ValueError("percent must be from 1 to 100")
    ordered = sorted(values)
    if not ordered:
        raise ValueError("no vora.turn EMF lines")
    rank = math.ceil(percent / 100 * len(ordered))
    return ordered[rank - 1]


def parse_emf_text(text: str) -> list[TurnSample]:
    """Return turn samples from EMF lines, log text, or a filter-log-events document."""
    return _parse_text(text, depth=0)


def summarize(turns: list[TurnSample]) -> dict[str, object]:
    """p50 and p95 for time to first word, STT, LLM, and TTS."""
    if not turns:
        raise ValueError("no vora.turn EMF lines")
    return {
        "method": "nearest-rank",
        "definition": (
            "Sort ascending. The p-th percentile is the value at 1-based rank ceil(p/100*n)."
        ),
        "n": len(turns),
        "tts_only": sum(1 for turn in turns if turn.tts_only),
        "p50": _percentile(turns, 50),
        "p95": _percentile(turns, 95),
        "turns": [asdict(turn) for turn in turns],
    }


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        if args:
            text = "\n".join(Path(path).read_text() for path in args)
        else:
            text = sys.stdin.read()
        report = summarize(parse_emf_text(text))
    except (EmfParseError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    json.dump(report, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def _percentile(turns: list[TurnSample], percent: int) -> dict[str, int]:
    return {
        field: nearest_rank((getattr(turn, field) for turn in turns), percent)
        for field in REPORT_FIELDS
    }


def _parse_text(text: str, *, depth: int) -> list[TurnSample]:
    if depth > _MAX_DEPTH:
        return []
    turns: list[TurnSample] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        value = _json_value(raw)
        if value is None:
            continue
        try:
            turns.extend(_from_value(value, depth=depth))
        except EmfParseError as exc:
            raise EmfParseError(f"line {lineno}: {exc}") from exc
    return turns


def _json_value(raw: str) -> object | None:
    line = raw.strip()
    start = line.find("{")
    array = line.find("[")
    if array >= 0 and (start < 0 or array < start):
        start = array
        end = line.rfind("]")
    else:
        end = line.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        return json.loads(line[start : end + 1])
    except json.JSONDecodeError:
        return None


def _from_value(value: object, *, depth: int) -> list[TurnSample]:
    if isinstance(value, list):
        turns: list[TurnSample] = []
        for item in value:
            turns.extend(_from_value(item, depth=depth))
        return turns
    if not isinstance(value, dict):
        return []
    if _is_vora_voice(value):
        return [_sample(value)]
    message = value.get("message")
    if isinstance(message, str):
        return _parse_text(message, depth=depth + 1)
    events = value.get("events")
    if isinstance(events, list):
        turns = []
        for event in events:
            turns.extend(_from_value(event, depth=depth + 1))
        return turns
    return []


def _is_vora_voice(payload: dict[str, object]) -> bool:
    aws = payload.get("_aws")
    if not isinstance(aws, dict):
        return False
    blocks = aws.get("CloudWatchMetrics")
    if not isinstance(blocks, list):
        return False
    return any(
        isinstance(block, dict) and block.get("Namespace") == "Vora/Voice" for block in blocks
    )


def _sample(payload: dict[str, object]) -> TurnSample:
    millis = {report: _millis(payload, worker) for worker, report in WORKER_FIELDS.items()}
    call_id = payload.get("call_id")
    aws = payload.get("_aws")
    timestamp = aws.get("Timestamp") if isinstance(aws, dict) else None
    return TurnSample(
        ttfw_ms=millis["ttfw_ms"],
        stt_ms=millis["stt_ms"],
        llm_ms=millis["llm_ms"],
        tts_ms=millis["tts_ms"],
        call_id=call_id if isinstance(call_id, str) else None,
        timestamp_ms=_timestamp(timestamp),
    )


def _millis(payload: dict[str, object], name: str) -> int:
    if name not in payload:
        raise EmfParseError(f"missing {name}")
    value = payload[name]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise EmfParseError(f"{name} is not a number")
    if isinstance(value, float) and not value.is_integer():
        raise EmfParseError(f"{name} is not a whole number of milliseconds")
    millis = int(value)
    if millis < 0:
        raise EmfParseError(f"{name} is negative")
    return millis


def _timestamp(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    millis = int(value)
    if millis < 0:
        return None
    return millis


if __name__ == "__main__":
    raise SystemExit(main())
