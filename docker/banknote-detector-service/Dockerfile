# Multi-stage build to reduce final image size
FROM python:3.11-slim as builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY docker/banknote-detector-service/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim

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

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

WORKDIR /app

COPY src/common /app/common
COPY src/banknote-detector-service/ .
COPY src/yolov7 /app/yolov7
RUN mkdir -p /app/logs

ENV PYTHONPATH=/app:/app/yolov7
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
