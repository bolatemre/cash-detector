FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for OpenCV and video processing
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgl1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY docker/celery-worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/celery-worker/ .

# Create necessary directories
RUN mkdir -p /app/logs
RUN mkdir -p /app/output/trigger/test

# Start Celery worker
# Note: Concurrency is configured via CELERY_WORKER_CONCURRENCY environment variable
CMD celery -A celery_app worker --loglevel=${LOG_LEVEL:-INFO} --concurrency=${CELERY_WORKER_CONCURRENCY:-4}


