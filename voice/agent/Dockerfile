FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

# Build from the repo root: docker build -f voice/agent/Dockerfile .
# uv.lock pins contracts at ../../packages/contracts, relative to this directory.
WORKDIR /opt/vora/voice/agent

COPY packages/contracts /opt/vora/packages/contracts
COPY voice/agent/pyproject.toml voice/agent/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY voice/agent/src ./src
RUN uv sync --frozen --no-dev
RUN uv run --no-dev python -m vora_agent.worker download-files

CMD ["uv", "run", "--no-dev", "python", "-m", "vora_agent.worker", "start"]
