from common.kafka_producer_config import KafkaProducerConfigMixin


class KafkaSettings(KafkaProducerConfigMixin):
    kafka_bootstrap_servers: str = "kafka:9093"
    kafka_topic: str = "pipeline-banknote-requests"
    kafka_group_id: str = "banknote-detector-service-group"
    kafka_stage_results_topic: str = "pipeline-stage-results"

    kafka_max_poll_interval_ms: int = 900000
    kafka_max_poll_records: int = 1
    kafka_session_timeout_ms: int = 45000
    kafka_heartbeat_interval_ms: int = 15000
    kafka_poll_timeout_ms: int = 1000
    kafka_processing_max_retries: int = 3
    kafka_processing_retry_backoff_seconds: float = 1.0
    kafka_dlq_topic: str = "banknote-dead-letter"
    kafka_producer_client_id: str = "banknote-detector-service"
    kafka_dlq_producer_client_id: str = "banknote-detector-service-consumer-dlq"
