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
    
    # Keycloak Configuration (required)
    keycloak_url: str  # e.g., http://keycloak:8080
    keycloak_realm: str  # e.g., security-realm
    keycloak_client_id: str  # e.g., security-service
    keycloak_client_secret: str  # Client secret for service-to-service auth
    
    # Kafka Configuration
    kafka_bootstrap_servers: str = "kafka:9093"
    kafka_uploaded_videos_topic: str = "uploaded-videos"
    
    # Application Configuration
    log_level: str = "INFO"
    
    # Camera Processing Configuration
    camera_max_failed_reads: int = 30  # Maximum consecutive failed frame reads before stopping
    camera_fps_log_interval: float = 1.0  # Interval in seconds for FPS logging
    camera_fps_warning_threshold: float = 1.0  # FPS threshold below which warning is logged
    camera_no_hand_timeout: float = 5.0  # Seconds to wait after hands disappear before stopping recording
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Global settings instance
settings = Settings()

