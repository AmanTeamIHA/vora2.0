import pytest

from vora_agent.call_start import PublicApiRejected, start_call


def test_start_call_posts_room_metadata_to_the_private_api() -> None:
    seen: dict[str, object] = {}

    def post(url: str, *, json: dict[str, str], headers: dict[str, str]) -> dict[str, object]:
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        return {
            "call_id": "call-1",
            "agent_version_id": "ver-1",
            "config": {"greeting": "Namaste", "llm": {"provider": "sarvam"}},
        }

    started = start_call(
        "http://api.vora2.local:8000",
        "service-secret",
        {"tenant_id": "ten", "agent_id": "agt"},
        post=post,
    )
    assert seen["url"] == "http://api.vora2.local:8000/internal/calls/start"
    assert seen["json"] == {"tenant_id": "ten", "agent_id": "agt"}
    assert seen["headers"] == {"x-vora-internal": "service-secret"}
    assert started.call_id == "call-1"
    assert started.agent_version_id == "ver-1"
    assert started.config.greeting == "Namaste"


def test_start_call_refuses_the_public_alb() -> None:
    def post(url: str, *, json: dict[str, str], headers: dict[str, str]) -> dict[str, object]:
        raise AssertionError(url)

    with pytest.raises(PublicApiRejected):
        start_call(
            "https://playground-dev.hellovora.ai",
            "service-secret",
            {"tenant_id": "ten", "agent_id": "agt"},
            post=post,
        )
