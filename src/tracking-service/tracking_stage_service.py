import logging
from typing import Any

from services.minio_service import MinioService
from script_tracking_no_vis import object_by_zones

logger = logging.getLogger(__name__)


class TrackingStageService:
    def __init__(self) -> None:
        self.minio_service = MinioService()

    def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        video_path = payload.get("video_path")
        bucket_name = payload.get("bucket_name")
        if not video_path:
            raise ValueError("video_path is required")

        logger.info(
            "Running tracking stage for camera=%s, video=%s",
            payload.get("camera_id"),
            video_path,
        )
        temp_file_path = self.minio_service.download_video_to_temp(video_path, bucket_name=bucket_name)
        if not temp_file_path:
            raise RuntimeError(f"Failed to download video from MinIO: {video_path}")
        try:
            return object_by_zones(temp_file_path)
        finally:
            self.minio_service.cleanup_temp_file(temp_file_path)
