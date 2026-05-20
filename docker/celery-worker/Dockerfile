# Multi-stage build to reduce final image size
FROM python:3.11-slim as builder

# Install build dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
WORKDIR /app
COPY docker/celery-worker/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage - minimal runtime image
FROM python:3.11-slim

# Install only runtime dependencies (no build tools)
# Note: EGL libraries required for MediaPipe (even in CPU mode, MediaPipe tries to initialize GPU context)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libgl1 \
    libegl1 \
    libgles2 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Set working directory
WORKDIR /app

# Copy application code
COPY src/common /app/common
COPY src/celery-worker/ .

ENV PYTHONPATH=/app

# Create necessary directories
RUN mkdir -p /app/logs /app/output/trigger/test

# Start Celery worker
# Note: Concurrency is configured via CELERY_WORKER_CONCURRENCY environment variable
CMD celery -A celery_app worker --loglevel=${LOG_LEVEL:-INFO} --concurrency=${CELERY_WORKER_CONCURRENCY:-4}


