# Playwright Python image — browser version matches locked playwright pip package.
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock .python-version ./
COPY packages/ingestion/pyproject.toml packages/ingestion/
COPY packages/ingestion/commission_ingestion packages/ingestion/commission_ingestion/

RUN uv sync --frozen --all-packages --all-extras

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["uv", "run", "retrieve-sources"]
