from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database Configuration
    database_url: str
    database_schema: str = "event_processor"
    
    # Kafka Configuration
    kafka_bootstrap_servers: str
    kafka_topic: str
    kafka_group_id: str
    
    # Email Configuration
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_from_email: str
    smtp_from_name: str = "Security System"
    
    # Notification Configuration
    notification_channels: str = "email"  # Comma-separated: "email,sms"
    
    # Master Service Configuration
    master_service_url: str = "http://master-service:8000"
    
    # Keycloak Configuration (required)
    keycloak_url: str  # e.g., http://keycloak:8080
    keycloak_realm: str  # e.g., security-realm
    keycloak_client_id: str  # e.g., security-service
    keycloak_client_secret: str  # Client secret for service-to-service auth
    
    # MinIO Configuration (required)
    minio_endpoint: str  # Internal endpoint for service access (e.g., minio:9000)
    minio_public_url: str = ""  # Public/external URL for email notifications (e.g., http://localhost:9000)
    minio_access_key: str
    minio_secret_key: str
    minio_bucket: str
    minio_secure: bool = False
    minio_suspicious_folder: str = "suspicious"  # Folder name for suspicious videos
    
    # Email Templates Configuration
    email_template_dir: str = "templates"
    email_html_template: str = "email_suspicious_event.html"
    
    # Application Configuration
    log_level: str = "INFO"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # Ignore extra fields from .env
    )
    
    @property
    def channels_list(self) -> List[str]:
        """Parse comma-separated notification channels"""
        return [ch.strip().lower() for ch in self.notification_channels.split(",") if ch.strip()]


# Global settings instance
settings = Settings()

