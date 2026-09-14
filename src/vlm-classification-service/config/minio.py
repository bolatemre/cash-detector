from pydantic_settings import BaseSettings


class MinioSettings(BaseSettings):
    minio_endpoint: str = "http://minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "security-videos"
    minio_secure: bool = False

    temp_video_dir: str = "/tmp/videos"
