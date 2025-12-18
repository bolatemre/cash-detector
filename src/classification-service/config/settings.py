from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for classification service"""
    
    # Kafka Configuration
    kafka_bootstrap_servers: str = "kafka:9093"
    kafka_topic: str = "uploaded-videos"
    kafka_group_id: str = "classification-service-group"
    kafka_security_events_topic: str = "security-events"
    
    # Kafka Consumer Configuration (for handling long-running video processing)
    kafka_max_poll_interval_ms: int = 900000  # 15 minutes - time allowed between poll() calls
    kafka_max_poll_records: int = 1  # Process one video at a time to avoid timeout
    kafka_session_timeout_ms: int = 45000  # 45 seconds - time to detect consumer failure
    kafka_heartbeat_interval_ms: int = 15000  # 15 seconds - heartbeat frequency
    
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
    yolo_model_path: str
    action_model_path: str
    object_class_id: int = 0  # Banknote class ID
    conf_threshold: float = 0.2  # YOLO confidence threshold
    target_interval: float = 0.1  # Frame sampling interval (seconds)
    sequence_length: int = 200  # Number of frames for sequence
    pose_min_detection_confidence: float = 0.3
    pose_min_tracking_confidence: float = 0.2
    features_min_threshold: int = 5  # Minimum features required to run classifier
    classification_confidence_threshold: float = 0.6  # If suspicious classification confidence is below this, treat as normal
    
    # YOLOv7 Custom Model Configuration
    yolov7_config_path: str = "../yolov7/cfg/training/yolov7_tiny_2cl.yaml"  # Relative to classification-service directory
    yolov7_device: str = "cpu"  # Device for YOLOv7 model (cpu/cuda)
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


settings = Settings()
