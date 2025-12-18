# Multi-stage build to reduce final image size
FROM python:3.11-slim as builder

# Install build dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
WORKDIR /app
COPY docker/master-service/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage - minimal runtime image
FROM python:3.11-slim

# Install only runtime dependencies
# Note: postgresql-client removed - not used (SQLAlchemy uses psycopg2)
RUN apt-get update && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Set working directory
WORKDIR /app

# Copy application code
COPY src/master-service/ .

# Create logs directory
RUN mkdir -p /app/logs

# Expose API port
EXPOSE 8000

# Run the application
CMD ["python", "main.py"]

