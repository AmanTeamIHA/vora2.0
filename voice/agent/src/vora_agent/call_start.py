from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

from vora_agent.config import AgentConfig, load_agent_config

_PUBLIC_HOSTS = frozenset({"playground-dev.hellovora.ai", "livekit-dev.hellovora.ai"})


class PublicApiRejected(Exception):
    """The worker must call the API on the private network, never the public ALB."""


@dataclass(frozen=True)
class StartedCall:
    call_id: str
    agent_version_id: str
    config: AgentConfig


def start_call(
    base_url: str,
    secret: str,
    metadata: dict[str, str],
    *,
    post: Callable[..., dict[str, object]],
) -> StartedCall:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "http" or host in _PUBLIC_HOSTS:
        raise PublicApiRejected(base_url)
    body = post(
        f"{base_url.rstrip('/')}/internal/calls/start",
        json={"tenant_id": metadata["tenant_id"], "agent_id": metadata["agent_id"]},
        headers={"x-vora-internal": secret},
    )
    config = body.get("config")
    if not isinstance(config, dict):
        raise ValueError("call start did not return a config")
    return StartedCall(
        call_id=str(body["call_id"]),
        agent_version_id=str(body["agent_version_id"]),
        config=load_agent_config(config),
    )
