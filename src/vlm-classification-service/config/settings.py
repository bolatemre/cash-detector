from pydantic_settings import SettingsConfigDict

from config.kafka import KafkaSettings
from config.mapping import MappingSettings
from config.minio import MinioSettings
from config.model import ModelSettings


class Settings(KafkaSettings, MinioSettings, ModelSettings, MappingSettings):
    """Configuration settings for VLM classification service."""

    log_level: str = "INFO"
    service_name: str = "vlm-classification-service"
    service_version: str = "1.0.0"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=(),
    )


settings = Settings()
