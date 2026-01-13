# Production Django Dockerfile - Multi-stage build
FROM python:3.12-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY ./backend/requirements /requirements
RUN pip install --user -r /requirements/production.txt

# Final production image
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/root/.local/bin:$PATH

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 django

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

WORKDIR /app

# Copy entrypoint and start scripts
COPY ./compose/production/django/entrypoint /entrypoint
RUN sed -i 's/\r$//g' /entrypoint && \
    chmod +x /entrypoint && \
    chown django /entrypoint

COPY ./compose/production/django/start /start
RUN sed -i 's/\r$//g' /start && \
    chmod +x /start && \
    chown django /start

# Copy application code
COPY --chown=django:django ./backend /app

# Create necessary directories
RUN mkdir -p /app/staticfiles /app/mediafiles && \
    chown -R django:django /app/staticfiles /app/mediafiles

USER django

ENTRYPOINT ["/entrypoint"]
