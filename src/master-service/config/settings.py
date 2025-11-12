from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database Configuration
    database_url: str
    database_schema: str = "master_service"
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_title: str = "Master Service API"
    api_version: str = "1.0.0"
    
    # Celery Configuration
    celery_broker_url: str = "redis://redis:6379/0"
    celery_result_backend: str = "redis://redis:6379/0"
    
    # Application Configuration
    log_level: str = "INFO"

    # Keycloak / Auth Configuration
    keycloak_server_url: str
    keycloak_realm: str
    keycloak_client_id: str
    keycloak_algorithms: str = "RS256"
    # Optional direct JWKS configuration
    keycloak_jwks_url: str | None = None
    jwks_cache_ttl_seconds: int = 300
    jwks_http_timeout_seconds: float = 5.0
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Global settings instance
settings = Settings()

