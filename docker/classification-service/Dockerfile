# Multi-stage build to reduce final image size
FROM python:3.11-slim as builder

# Install build dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
WORKDIR /app
COPY docker/classification-service/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage - minimal runtime image
FROM python:3.11-slim

# Install only runtime dependencies (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

WORKDIR /app

COPY src/common /app/common
COPY src/classification-service/ .
COPY src/yolov7 /app/yolov7
RUN mkdir -p /app/logs

ENV PYTHONPATH=/app:/app/yolov7
ENV PYTHONUNBUFFERED=1

EXPOSE 8001

CMD ["python", "main.py"]
