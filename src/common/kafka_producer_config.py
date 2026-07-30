"""Shared confluent-kafka producer settings for service configuration classes."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class KafkaProducerConfigMixin(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    kafka_producer_client_id: str = "kafka-producer"
    kafka_producer_acks: str = "all"
    kafka_producer_retries: int = 3
    kafka_producer_retry_backoff_ms: int = 100
    kafka_producer_flush_timeout_seconds: float = 10.0

    kafka_dlq_producer_client_id: str = "kafka-consumer-dlq"
    kafka_dlq_producer_flush_timeout_seconds: float = 5.0
    kafka_consumer_auto_offset_reset: str = "earliest"

    def build_kafka_producer_config(self, client_id: str | None = None) -> dict[str, str | int]:
        return {
            "bootstrap.servers": self.kafka_bootstrap_servers,
            "client.id": client_id or self.kafka_producer_client_id,
            "acks": self.kafka_producer_acks,
            "retries": self.kafka_producer_retries,
            "retry.backoff.ms": self.kafka_producer_retry_backoff_ms,
        }
