import logging

from adapters.minio_service import MinioObjectNotFoundError, MinioService
from common.kafka_messages import BanknoteStageResult, PipelineStageEnvelope
from config.settings import Settings
from detection.yolo_model import YOLOv7Model

logger = logging.getLogger(__name__)


class BanknoteInvalidRequestError(ValueError):
    """Stage request cannot be processed; Kafka should not retry the message."""

    retryable = False


class BanknoteStageService:
    def __init__(self, settings: Settings) -> None:
        self._minio = MinioService(settings)
        self._model = YOLOv7Model(settings)

    def process(self, job: PipelineStageEnvelope) -> BanknoteStageResult:
        temp_file_path = None
        try:
            logger.info(
                "Running banknote detection stage for camera=%s, video=%s, correlation_id=%s",
                job.camera_id,
                job.video_path,
                job.correlation_id,
            )
            if not job.video_path:
                raise BanknoteInvalidRequestError("stage request is missing video_path")

            temp_file_path = self._minio.download_video_to_temp(
                job.video_path, bucket_name=job.bucket_name
            )
            detected = self._model.any_banknote_in_video(temp_file_path)
            result = BanknoteStageResult(
                event_type="detected" if detected else "not_detected",
                detected=detected,
            )
            logger.info(
                "Banknote detection result for %s: %s",
                job.video_path,
                result.event_type,
            )
            return result
        except (BanknoteInvalidRequestError, MinioObjectNotFoundError):
            raise
        except Exception:
            logger.error("Error during banknote detection stage", exc_info=True)
            raise
        finally:
            if temp_file_path:
                self._minio.cleanup_temp_file(temp_file_path)
