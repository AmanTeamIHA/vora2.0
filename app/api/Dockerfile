FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["sh", "-c", "uv run --no-dev alembic upgrade head && uv run --no-dev uvicorn vora_api.main:app --host 0.0.0.0 --port 8000"]
