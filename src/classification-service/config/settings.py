import os
from typing import Optional


class Settings:
    """Configuration settings for classification service"""
    
    # Kafka Configuration
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9093")
    kafka_topic: str = os.getenv("KAFKA_TOPIC", "uploaded-videos")
    kafka_group_id: str = os.getenv("KAFKA_GROUP_ID", "classification-service-group")
    kafka_security_events_topic: str = os.getenv("KAFKA_SECURITY_EVENTS_TOPIC", "security-events")
    
    # MinIO Configuration
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "minio:9000")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    minio_bucket: str = os.getenv("MINIO_BUCKET", "security-videos")
    minio_secure: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"
    
    # Local storage for downloaded videos
    temp_video_dir: str = os.getenv("TEMP_VIDEO_DIR", "/tmp/videos")
    
    # Logging Configuration
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Service Configuration
    service_name: str = "classification-service"
    service_version: str = "1.0.0"
    
    # TODO: Add classification model configuration


settings = Settings()
