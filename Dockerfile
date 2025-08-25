# Multi-stage Dockerfile for ISCC Hub
# Supports development and production environments

# Base stage with UV installer
FROM python:3.12-slim AS base

# Install UV using the official installer
COPY --from=ghcr.io/astral-sh/uv:0.5.16 /uv /usr/local/bin/uv

# Set common environment variables
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1

# Set working directory
WORKDIR /app

# Development stage
FROM base AS development

# Install development tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install all dependencies including dev
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --dev

# Copy entire project for development
COPY . .

# Install project in editable mode
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --dev

# Copy and setup entrypoint script
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create data directory
RUN mkdir -p /app/data

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]

# Production stage
FROM base AS production

# Build-time arguments for version metadata
ARG BUILD_COMMIT="unknown"
ARG BUILD_TAG="unknown"
ARG BUILD_TIMESTAMP="unknown"

# Set build metadata as environment variables
ENV BUILD_COMMIT=${BUILD_COMMIT} \
    BUILD_TAG=${BUILD_TAG} \
    BUILD_TIMESTAMP=${BUILD_TIMESTAMP}

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install production dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy application code
COPY iscc_hub/ ./iscc_hub/
COPY scripts/ ./scripts/
COPY manage.py ./

# Install the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Copy entrypoint script
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create data directory
RUN mkdir -p /app/data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT:-8000}/health || exit 1

# Expose default port
EXPOSE 8000

# Use the entrypoint script
ENTRYPOINT ["/entrypoint.sh"]