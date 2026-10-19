from pydantic_settings import SettingsConfigDict

from config.kafka import KafkaSettings
from config.minio import MinioSettings
from config.model import ModelSettings


class Settings(KafkaSettings, MinioSettings, ModelSettings):
    """Configuration settings for YOLOv7 banknote detection."""

    log_level: str = "INFO"
    service_name: str = "banknote-detector-service"
    service_version: str = "1.0.0"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=(),
    )


settings = Settings()
