# syntax=docker/dockerfile:1
FROM python:3.13-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.9.8 /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN uv sync --frozen --no-dev --no-install-project

# Copy source
COPY src/ ./src/

FROM python:3.13-slim

ARG BUILD_VERSION=dev
ENV BOT_VERSION=${BUILD_VERSION}

# Create non-root user
RUN useradd --uid 10001 --no-create-home --shell /bin/false appuser

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy source and config
COPY --from=builder /app/src ./src
COPY config.toml ./

# Set ownership and switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Add venv to path
ENV PATH="/app/.venv/bin:$PATH"

# Run bot
CMD ["python", "-m", "src.main"]

# Labels for versioning
# Build with: docker build -t workshop-bot:v1.0 .
# Tag format: v<MAJOR>.<MINOR>
