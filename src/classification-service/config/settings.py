from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for classification service"""
    
    # Kafka Configuration
    kafka_bootstrap_servers: str = "kafka:9093"
    kafka_topic: str = "uploaded-videos"
    kafka_group_id: str = "classification-service-group"
    kafka_security_events_topic: str = "security-events"
    
    # MinIO Configuration
    minio_endpoint: str = "http://minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "security-videos"
    minio_secure: bool = False
    
    # Local storage for downloaded videos
    temp_video_dir: str = "/tmp/videos"
    
    # Logging Configuration
    log_level: str = "INFO"
    
    # Service Configuration
    service_name: str = "classification-service"
    service_version: str = "1.0.0"
    
    # Classification Model Configuration
    yolo_model_path: str = "best_gpu.pt"
    action_model_path: str = "clf6.h5"
    object_class_id: int = 0  # Banknote class ID
    conf_threshold: float = 0.2  # YOLO confidence threshold
    target_interval: float = 0.1  # Frame sampling interval (seconds)
    sequence_length: int = 200  # Number of frames for sequence
    pose_min_detection_confidence: float = 0.3
    pose_min_tracking_confidence: float = 0.2
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


settings = Settings()
