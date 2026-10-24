FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/

# Repo-root build context. The contracts path dependency is ../../packages/contracts
# relative to this directory, same as a local checkout.
WORKDIR /src/app/api

COPY packages/contracts /src/packages/contracts
COPY app/api/pyproject.toml app/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app/api/src ./src
COPY app/api/calls/__init__.py app/api/calls/consumer.py app/api/calls/persist.py app/api/calls/redis_stream.py ./calls/
COPY app/api/alembic ./alembic
COPY app/api/alembic.ini ./
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["sh", "-c", "uv run --no-dev alembic upgrade head && uv run --no-dev uvicorn vora_api.main:app --host 0.0.0.0 --port 8000"]
