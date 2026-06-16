# ==============================================================================
# Multi-stage production Dockerfile for EVAP FastAPI backend
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: builder — install Python dependencies
# ------------------------------------------------------------------------------
FROM python:3.13-slim AS builder

# Install build deps for psycopg2, OpenCV, and other native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender-dev \
        libgl1-mesa-glx \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .

# Install into a prefix so we can copy cleanly to the final image
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ------------------------------------------------------------------------------
# Stage 2: runtime
# ------------------------------------------------------------------------------
FROM python:3.13-slim AS base

LABEL maintainer="evap-team@beamlab.dev" \
      version="4.0.0" \
      description="EVAP Enterprise Video Analytics Platform – FastAPI backend"

# Runtime system libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libgl1-mesa-glx \
        libgomp1 \
        curl \
        tini \
    && rm -rf /var/lib/apt/lists/*

# ---- NVIDIA GPU support (uncomment the lines below and rebuild with --build-arg GPU=1)
# ARG GPU=0
# RUN if [ "$GPU" = "1" ]; then \
#         apt-get update && apt-get install -y --no-install-recommends \
#             nvidia-cuda-toolkit \
#         && rm -rf /var/lib/apt/lists/*; \
#     fi
# ENV NVIDIA_VISIBLE_DEVICES=all
# ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility
# To use GPU at runtime, start the container with:
#   docker run --gpus all evap-backend:4.0.0

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Non-root user
RUN groupadd --gid 1001 evap \
    && useradd --uid 1001 --gid evap --shell /bin/bash --create-home evap

WORKDIR /app

# Copy application source
COPY --chown=evap:evap . .

# Application environment defaults (override at runtime via env or .env)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    APP_ENV=production \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    WORKERS=4 \
    LOG_LEVEL=info \
    SNAPSHOTS_DIR=/app/snapshots \
    TZ=UTC

# Writable directories
RUN mkdir -p /app/snapshots /app/logs \
    && chown -R evap:evap /app/snapshots /app/logs

USER evap

EXPOSE 8000

# Health check against /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use tini as PID 1 so signals propagate correctly to uvicorn
ENTRYPOINT ["/usr/bin/tini", "--"]

CMD ["sh", "-c", "uvicorn app.main:app \
        --host ${APP_HOST} \
        --port ${APP_PORT} \
        --workers ${WORKERS} \
        --log-level ${LOG_LEVEL} \
        --proxy-headers \
        --forwarded-allow-ips='*'"]
