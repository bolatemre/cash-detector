FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY docker/event-processor/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code from the src/event-processor directory
COPY src/event-processor/ .

# Create logs directory
RUN mkdir -p /app/logs

# Run the event processor
CMD ["python", "main.py"]

