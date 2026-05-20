from common.kafka_producer_config import KafkaProducerConfigMixin
from pydantic import Field
from pydantic_settings import SettingsConfigDict


class Settings(KafkaProducerConfigMixin):
    """Configuration settings for tracking service."""

    # Kafka
    kafka_bootstrap_servers: str = "kafka:9093"
    kafka_topic: str = "pipeline-tracking-requests"
    kafka_group_id: str = "tracking-service-group"
    kafka_stage_results_topic: str = "pipeline-stage-results"
    kafka_max_poll_interval_ms: int = 900000
    kafka_max_poll_records: int = 1
    kafka_session_timeout_ms: int = 45000
    kafka_heartbeat_interval_ms: int = 15000
    kafka_poll_timeout_ms: int = 1000
    kafka_processing_max_retries: int = 3
    kafka_processing_retry_backoff_seconds: float = 1.0
    kafka_dlq_topic: str = "tracking-dead-letter"
    kafka_producer_client_id: str = "tracking-service"
    kafka_dlq_producer_client_id: str = "tracking-service-consumer-dlq"

    # MinIO
    minio_endpoint: str = "http://minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "security-videos"
    minio_secure: bool = False
    temp_video_dir: str = "/tmp/videos"

    # Logging / service
    log_level: str = "INFO"
    service_name: str = "tracking-service"
    service_version: str = "1.0.0"

    # Tracking model
    tracking_model_path: str
    yolov7_config_path: str = "yolov7/cfg/training/yolov7_tiny_2cl.yaml"
    yolov7_device: str = "cpu"
    conf_threshold: float = 0.45
    iou_threshold: float = 0.45
    target_interval: float = 0.1
    yolo_img_size: int = 640
    class_names: list[str] = Field(default_factory=lambda: ["banknote", "cash register"])
    position_threshold: int = 100
    min_area: int = 100
    deepsort_config: dict = Field(
        default_factory=lambda: {
            "max_age": 10,
            "n_init": 1,
            "max_iou_distance": 0.6,
            "embedder": "mobilenet",
            "bgr": True,
            "nn_budget": 50,
        }
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
