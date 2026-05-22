from typing import Optional

from common.kafka_producer_config import KafkaProducerConfigMixin
from pydantic_settings import SettingsConfigDict


class Settings(KafkaProducerConfigMixin):
    """Configuration settings for classification service"""
    
    # Kafka Configuration
    kafka_bootstrap_servers: str = "kafka:9093"
    kafka_topic: str = "pipeline-classification-requests"
    kafka_group_id: str = "classification-service-group"
    kafka_security_events_topic: str = "security-events"
    kafka_stage_results_topic: str = "pipeline-stage-results"
    
    # Kafka Consumer Configuration
    kafka_max_poll_interval_ms: int = 900000  # Safety net; poll loop stays active during worker processing
    kafka_max_poll_records: int = 1  # One message in-flight at a time
    kafka_session_timeout_ms: int = 45000  # 45 seconds - time to detect consumer failure
    kafka_heartbeat_interval_ms: int = 15000  # 15 seconds - heartbeat frequency
    kafka_poll_timeout_ms: int = 1000
    kafka_processing_max_retries: int = 3
    kafka_processing_retry_backoff_seconds: float = 1.0
    kafka_dlq_topic: str = "classification-dead-letter"
    kafka_producer_client_id: str = "classification-service"
    kafka_dlq_producer_client_id: str = "classification-service-consumer-dlq"

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
    yolov7_config_path: str = "yolov7/cfg/training/yolov7_tiny_2cl.yaml"  # Under service dir (/app) or sibling src/yolov7 locally
    yolov7_device: str = "cpu"  # Device for YOLOv7 model (cpu/cuda)
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


settings = Settings()
