from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database Configuration
    database_url: str
    
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
    notification_recipients: str
    notification_channels: str = "email"  # Comma-separated: "email,sms"
    
    # MinIO Configuration (required)
    minio_endpoint: str
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
    def recipients_list(self) -> List[str]:
        """Parse comma-separated email recipients"""
        return [email.strip() for email in self.notification_recipients.split(",") if email.strip()]
    
    @property
    def channels_list(self) -> List[str]:
        """Parse comma-separated notification channels"""
        return [ch.strip().lower() for ch in self.notification_channels.split(",") if ch.strip()]


# Global settings instance
settings = Settings()

