#!/usr/bin/env python3
"""Render LiveKit config on the host and start the compose stack.

API key and secret are read from Secrets Manager at boot. They are not in git
and not in EC2 user data.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path("/opt/vora2/livekit")
TEMPLATES = ROOT / "templates"
RUN = ROOT / "run"
SECRET_ID = "vora2/dev/livekit"
REGION = "ap-south-1"

PLACEHOLDERS = (
    "__NODE_IP__",
    "__REDIS_ADDRESS__",
    "__HOSTNAME__",
    "__RECORDINGS_BUCKET__",
    "__API_KEY__",
    "__API_SECRET__",
)

FILES = ("livekit.yaml", "sip.yaml", "egress.yaml", "Caddyfile")


def render_text(text: str, values: dict[str, str]) -> str:
    missing = [key for key in PLACEHOLDERS if key not in values]
    if missing:
        raise ValueError(f"missing values for {', '.join(missing)}")
    for key in PLACEHOLDERS:
        value = values[key]
        if not value or any(token in value for token in PLACEHOLDERS):
            raise ValueError(f"refusing empty or nested value for {key}")
        text = text.replace(key, value)
    leftover = [key for key in PLACEHOLDERS if key in text]
    if leftover:
        raise ValueError(f"unrendered placeholder: {', '.join(leftover)}")
    return text


def _imds_public_ip() -> str:
    token_request = urllib.request.Request(
        "http://169.254.169.254/latest/api/token",
        method="PUT",
        headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
    )
    with urllib.request.urlopen(token_request, timeout=2) as response:
        token = response.read().decode()
    ip_request = urllib.request.Request(
        "http://169.254.169.254/latest/meta-data/public-ipv4",
        headers={"X-aws-ec2-metadata-token": token},
    )
    with urllib.request.urlopen(ip_request, timeout=2) as response:
        return response.read().decode().strip()


def wait_for_eip(expected: str) -> None:
    for _ in range(90):
        try:
            if _imds_public_ip() == expected:
                return
        except Exception:
            pass
        time.sleep(2)
    raise SystemExit("public IPv4 did not become the LiveKit Elastic IP")


def read_secret() -> dict[str, str]:
    for _ in range(30):
        proc = subprocess.run(
            [
                "aws",
                "secretsmanager",
                "get-secret-value",
                "--secret-id",
                SECRET_ID,
                "--region",
                REGION,
                "--query",
                "SecretString",
                "--output",
                "text",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            loaded = json.loads(proc.stdout)
            return {
                "api_key": str(loaded["api_key"]),
                "api_secret": str(loaded["api_secret"]),
            }
        time.sleep(4)
    raise SystemExit("could not read vora2/dev/livekit")


def write_configs(values: dict[str, str]) -> None:
    RUN.mkdir(mode=0o750, exist_ok=True)
    for name in FILES:
        rendered = render_text((TEMPLATES / name).read_text(), values)
        dest = RUN / name
        dest.write_text(rendered)
        dest.chmod(0o640)


def main() -> None:
    expected = os.environ["VORA_NODE_IP"]
    wait_for_eip(expected)
    secret = read_secret()
    write_configs(
        {
            "__NODE_IP__": expected,
            "__REDIS_ADDRESS__": os.environ["VORA_REDIS_ADDRESS"],
            "__HOSTNAME__": os.environ["VORA_LIVEKIT_HOSTNAME"],
            "__RECORDINGS_BUCKET__": os.environ["VORA_RECORDINGS_BUCKET"],
            "__API_KEY__": secret["api_key"],
            "__API_SECRET__": secret["api_secret"],
        }
    )
    subprocess.run(
        ["docker", "compose", "-f", str(ROOT / "docker-compose.yml"), "up", "-d", "--remove-orphans"],
        check=True,
    )


if __name__ == "__main__":
    main()
