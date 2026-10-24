FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev
RUN uv run --no-dev python -m vora_agent.worker download-files

CMD ["uv", "run", "--no-dev", "python", "-m", "vora_agent.worker", "start"]
