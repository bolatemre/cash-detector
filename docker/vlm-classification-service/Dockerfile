FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

# Qwen3-VL-FP8 uses Triton kernels that JIT-compile on first generate(); gcc is required.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

WORKDIR /app
COPY docker/vlm-classification-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/common /app/common
COPY src/vlm-classification-service/ .
RUN mkdir -p /app/logs /tmp/videos /root/.cache/huggingface

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/root/.cache/huggingface
ENV CC=gcc
ENV CXX=g++

CMD ["python", "main.py"]
