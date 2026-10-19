import logging
import os
import tempfile

from minio import Minio
from minio.error import S3Error

from config.minio import MinioSettings

logger = logging.getLogger(__name__)

_MISSING_OBJECT_CODES = frozenset(
    {"NoSuchKey", "NoSuchBucket", "NoSuchObject", "NotFound"}
)


class MinioObjectNotFoundError(LookupError):
    """Object or bucket does not exist; Kafka should not retry the message."""

    retryable = False


class MinioDownloadError(RuntimeError):
    """Transient MinIO or network failure; Kafka may retry the message."""


def _is_missing_object_error(error: S3Error) -> bool:
    code = (error.code or "").strip()
    if code in _MISSING_OBJECT_CODES:
        return True
    response = getattr(error, "response", None)
    status = getattr(response, "status", None)
    return status == 404


class MinioService:
    def __init__(self, settings: MinioSettings) -> None:
        endpoint = settings.minio_endpoint.replace("http://", "").replace("https://", "")

        self.client = Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self.bucket = settings.minio_bucket
        self.temp_dir = settings.temp_video_dir

        os.makedirs(self.temp_dir, exist_ok=True)
        logger.info("MinIO service initialized: %s/%s, temp dir: %s", endpoint, self.bucket, self.temp_dir)

    def download_video_to_temp(self, video_path: str, bucket_name: str | None = None) -> str:
        temp_file_path = None
        bucket = bucket_name or self.bucket
        try:
            filename = os.path.basename(video_path)
            file_extension = os.path.splitext(filename)[1]

            temp_file = tempfile.NamedTemporaryFile(
                suffix=file_extension,
                delete=False,
                dir=self.temp_dir,
            )
            temp_file_path = temp_file.name
            temp_file.close()

            logger.info("Downloading video from MinIO: %s/%s", bucket, video_path)

            self.client.fget_object(
                bucket_name=bucket,
                object_name=video_path,
                file_path=temp_file_path,
            )

            logger.info("Video downloaded successfully to: %s", temp_file_path)
            downloaded_path = temp_file_path
            temp_file_path = None
            return downloaded_path

        except S3Error as e:
            logger.error("MinIO S3 error while downloading %s: %s", video_path, e)
            if _is_missing_object_error(e):
                raise MinioObjectNotFoundError(
                    f"Video not found in MinIO: {bucket}/{video_path}"
                ) from e
            raise MinioDownloadError(
                f"MinIO S3 error while downloading {video_path}: {e}"
            ) from e
        except Exception as e:
            logger.error("Error downloading video from MinIO: %s", e, exc_info=True)
            raise MinioDownloadError(
                f"Error downloading video from MinIO: {e}"
            ) from e
        finally:
            if temp_file_path:
                self.cleanup_temp_file(temp_file_path)

    def cleanup_temp_file(self, file_path: str | None) -> bool:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.info("Cleaned up temporary file: %s", file_path)
            return True
        except Exception as e:
            logger.error("Error cleaning up temporary file %s: %s", file_path, e)
            return False
