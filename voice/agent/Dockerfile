FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

# Build from the repo root: docker build -f voice/agent/Dockerfile .
# The lockfile path is ../../packages/contracts. uv refuses that path from
# /app because /app/../.. climbs above the filesystem root.
COPY packages/contracts /opt/vora/packages/contracts

WORKDIR /opt/vora/voice/agent
COPY voice/agent/pyproject.toml voice/agent/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY voice/agent/src ./src
RUN uv sync --frozen --no-dev
RUN uv run --no-dev python -m vora_agent.worker download-files

CMD ["uv", "run", "--no-dev", "python", "-m", "vora_agent.worker", "start"]
