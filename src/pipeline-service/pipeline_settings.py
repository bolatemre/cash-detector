from common.kafka_producer_config import KafkaProducerConfigMixin
from pydantic_settings import SettingsConfigDict


class PipelineSettings(KafkaProducerConfigMixin):
    # Kafka
    kafka_bootstrap_servers: str = "kafka:9093"
    kafka_uploaded_videos_topic: str = "uploaded-videos"
    kafka_stage_results_topic: str = "pipeline-stage-results"
    kafka_classification_requests_topic: str = "pipeline-classification-requests"
    kafka_tracking_requests_topic: str = "pipeline-tracking-requests"
    kafka_vlm_requests_topic: str = "pipeline-vlm-requests"
    kafka_group_id: str = "pipeline-service-group"
    kafka_security_events_topic: str = "security-events"
    kafka_max_poll_interval_ms: int = 900000
    kafka_max_poll_records: int = 1
    kafka_session_timeout_ms: int = 45000
    kafka_heartbeat_interval_ms: int = 15000
    kafka_poll_timeout_ms: int = 1000
    kafka_processing_max_retries: int = 3
    kafka_processing_retry_backoff_seconds: float = 1.0
    kafka_dlq_topic: str = "pipeline-dead-letter"

    kafka_producer_client_id: str = "pipeline-service"
    kafka_dlq_producer_client_id: str = "pipeline-service-consumer-dlq"

    # MinIO
    minio_endpoint: str = "http://minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "security-videos"
    minio_secure: bool = False
    minio_public_url: str = "http://localhost:9000"

    # Pipeline behavior
    stage_order: str = "classification,tracking"
    alert_labels: str = "suspicious,alert"
    classification_confidence_threshold: float = 0.8
    unknown_label: str = "unknown"
    service_name: str = "pipeline-service"
    service_version: str = "1.0.0"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

settings = PipelineSettings()
