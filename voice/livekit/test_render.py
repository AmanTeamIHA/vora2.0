import unittest
from pathlib import Path

from render import PLACEHOLDERS, render_text

CONFIGS = Path(__file__).parent

VALUES = {
    "__NODE_IP__": "203.0.113.10",
    "__REDIS_ADDRESS__": "vora2-dev.cache.amazonaws.com:6379",
    "__HOSTNAME__": "livekit-dev.hellovora.ai",
    "__RECORDINGS_BUCKET__": "vora2-dev-recordings",
    "__API_KEY__": "devexamplekey",
    "__API_SECRET__": "examplesecretvalue",
}


class RenderTest(unittest.TestCase):
    def test_replaces_every_placeholder(self) -> None:
        text = " ".join(PLACEHOLDERS)
        rendered = render_text(text, VALUES)
        self.assertEqual(
            rendered,
            "203.0.113.10 vora2-dev.cache.amazonaws.com:6379 "
            "livekit-dev.hellovora.ai vora2-dev-recordings devexamplekey examplesecretvalue",
        )
        for key in PLACEHOLDERS:
            self.assertNotIn(key, rendered)

    def test_rejects_a_leftover_placeholder(self) -> None:
        with self.assertRaises(ValueError):
            render_text("still __API_SECRET__ here", VALUES | {"__API_SECRET__": "__API_SECRET__"})

    def test_rejects_an_empty_value(self) -> None:
        with self.assertRaises(ValueError):
            render_text("ip __NODE_IP__", VALUES | {"__NODE_IP__": ""})

    def test_shipped_configs_render(self) -> None:
        for name in ("livekit.yaml", "sip.yaml", "egress.yaml", "Caddyfile"):
            rendered = render_text((CONFIGS / name).read_text(), VALUES)
            for key in PLACEHOLDERS:
                self.assertNotIn(key, rendered, name)


if __name__ == "__main__":
    unittest.main()
