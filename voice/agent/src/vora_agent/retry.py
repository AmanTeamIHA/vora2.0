import random
from collections.abc import Callable

RATE_LIMIT_CLOSE = 1003


class WebsocketClosed(Exception):
    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def backoff_delay(
    attempt: int,
    rng: random.Random,
    *,
    base: float = 0.25,
    cap: float = 8.0,
) -> float:
    """Full jitter inside an exponential window. Attempt 0 stays within `base`."""
    window = min(cap, base * (2**attempt))
    return rng.uniform(0, window)


def open_with_backoff[T](
    connect: Callable[[], T],
    *,
    sleep: Callable[[float], None],
    rng: random.Random,
    log: Callable[[str], None],
    max_attempts: int = 5,
) -> T:
    """Open a Sarvam socket. Close code 1003 is a rate limit: back off and retry."""
    last: WebsocketClosed | None = None
    for attempt in range(max_attempts):
        sleep(backoff_delay(attempt, rng))
        try:
            return connect()
        except WebsocketClosed as exc:
            last = exc
            if exc.code != RATE_LIMIT_CLOSE:
                raise
            log("sarvam_rate_limited")
    assert last is not None
    raise last
