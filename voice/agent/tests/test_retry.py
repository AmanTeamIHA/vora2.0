import random

import pytest

from vora_agent.retry import WebsocketClosed, backoff_delay, open_with_backoff


def test_backoff_is_full_jitter_inside_the_exponential_window() -> None:
    rng = random.Random(7)
    first = backoff_delay(0, rng)
    second = backoff_delay(3, rng)
    assert 0 <= first <= 0.25
    assert 0 <= second <= 2.0


def test_close_1003_retries_and_logs_sarvam_rate_limited() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []
    logs: list[str] = []

    def connect() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise WebsocketClosed(1003)
        return "open"

    result = open_with_backoff(
        connect,
        sleep=sleeps.append,
        rng=random.Random(1),
        log=logs.append,
        max_attempts=4,
    )
    assert result == "open"
    assert calls["n"] == 3
    assert logs == ["sarvam_rate_limited", "sarvam_rate_limited"]
    assert len(sleeps) == 3
    assert all(delay >= 0 for delay in sleeps)


def test_other_close_codes_are_not_retried() -> None:
    def connect() -> str:
        raise WebsocketClosed(1006)

    with pytest.raises(WebsocketClosed) as raised:
        open_with_backoff(
            connect,
            sleep=lambda _delay: None,
            rng=random.Random(0),
            log=lambda _event: None,
            max_attempts=4,
        )
    assert raised.value.code == 1006
