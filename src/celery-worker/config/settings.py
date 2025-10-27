from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Celery Configuration
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/0"
    celery_worker_concurrency: int = 4
    
    # Task Retry Configuration
    celery_task_max_retries: Optional[int] = None  # Unlimited retry attempts (None = infinite)
    celery_task_retry_backoff: int = 300  # Fixed delay in seconds (5 minutes)
    celery_task_retry_backoff_max: int = 300  # Maximum delay between retries (same as backoff for no exponential)
    celery_task_retry_jitter: bool = False  # No jitter for fixed retry intervals
    
    @field_validator('celery_task_max_retries', mode='before')
    @classmethod
    def parse_max_retries(cls, v):
        """Convert empty string to None for unlimited retries"""
        if v == '' or v is None:
            return None
        return int(v)
    
    # Master Service Configuration
    master_service_url: str = "http://master-service:8000"
    
    # Kafka Configuration
    kafka_bootstrap_servers: str = "kafka:9093"
    kafka_uploaded_videos_topic: str = "uploaded-videos"
    
    # Application Configuration
    log_level: str = "INFO"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Global settings instance
settings = Settings()

