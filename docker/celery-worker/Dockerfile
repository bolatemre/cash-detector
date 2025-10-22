FROM python:3.11-slim

WORKDIR /app

# Install basic system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# TODO: Uncomment when implementing video processing
# Install system dependencies for OpenCV
# RUN apt-get update && apt-get install -y \
#     g++ \
#     libglib2.0-0 \
#     libsm6 \
#     libxext6 \
#     libxrender-dev \
#     libgomp1 \
#     libgl1-mesa-glx \
#     ffmpeg \
#     && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY docker/celery-worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/celery-worker/ .

# Create logs directory
RUN mkdir -p /app/logs

# Start Celery worker
CMD ["celery", "-A", "celery_app", "worker", "--loglevel=info", "--concurrency=2"]


