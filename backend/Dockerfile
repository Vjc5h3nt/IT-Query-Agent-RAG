FROM python:3.12-slim AS base

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev deps, cached layer)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY app/ app/
COPY services/ services/
COPY database/ database/
COPY scripts/ scripts/
COPY .env.example .env.example

# Create storage directories
RUN mkdir -p /app/data /app/storage/chroma_db /app/storage/temp

ENV PYTHONUNBUFFERED=1
ENV DATA_FOLDER=/app/data
ENV STORAGE_FOLDER=/app/storage
ENV CHROMA_DB_PATH=/app/storage/chroma_db
ENV SESSION_DB_PATH=/app/storage/sessions.db

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
