"""Pace Sarvam STT and TTS websocket opens. Close 1003 retries with backoff."""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

import aiohttp

from vora_agent.retry import RATE_LIMIT_CLOSE, WebsocketClosed, backoff_delay

logger = logging.getLogger("vora.agent")
_installed = False


async def open_paced[T](
    connect: Callable[[], Awaitable[T]],
    *,
    rng: random.Random | None = None,
    max_attempts: int = 5,
) -> T:
    source = rng or random.Random()
    last: WebsocketClosed | None = None
    for attempt in range(max_attempts):
        await asyncio.sleep(backoff_delay(attempt, source))
        try:
            socket = await connect()
        except WebsocketClosed as exc:
            last = exc
            if exc.code != RATE_LIMIT_CLOSE:
                raise
            logger.warning("sarvam_rate_limited")
            continue
        code = getattr(socket, "close_code", None)
        if code == RATE_LIMIT_CLOSE:
            last = WebsocketClosed(RATE_LIMIT_CLOSE)
            logger.warning("sarvam_rate_limited")
            continue
        return socket
    assert last is not None
    raise last


def install_sarvam_pacing() -> None:
    """Wrap aiohttp websocket opens to Sarvam. Other hosts are unchanged."""
    global _installed
    if _installed:
        return
    original = aiohttp.ClientSession.ws_connect

    async def ws_connect(self: aiohttp.ClientSession, url: object, *args: object, **kwargs: object):
        if "sarvam.ai" not in str(url):
            return await original(self, url, *args, **kwargs)

        async def connect() -> aiohttp.ClientWebSocketResponse:
            return await original(self, url, *args, **kwargs)

        return await open_paced(connect)

    aiohttp.ClientSession.ws_connect = ws_connect  # type: ignore[method-assign]
    _installed = True
