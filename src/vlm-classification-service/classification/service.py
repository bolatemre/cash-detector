import logging
import time
import traceback

import torch
import gc

from adapters.minio_service import MinioObjectNotFoundError, MinioService
from classification.frame_extractor import FrameExtractor
from classification.result_mapper import ResultMapper, VlmInvalidJsonError
from classification.vlm_model import VlmModel
from common.kafka_messages import PipelineStageEnvelope, VlmStageResult
from config.settings import Settings

logger = logging.getLogger(__name__)


class VlmInvalidRequestError(ValueError):
    """Stage request cannot be processed; Kafka should not retry the message."""

    retryable = False


class VlmClassificationService:
    """Download a video from MinIO and classify it with the VLM."""

    def __init__(self, settings: Settings):
        self._settings = settings
        self._minio = MinioService(settings)
        self._frames = FrameExtractor(settings)
        self._model = VlmModel(settings)
        self._mapper = ResultMapper(settings)
        logger.info("%s initialized", settings.service_name)

    def process(self, job: PipelineStageEnvelope) -> VlmStageResult:
        temp_file_path = None
        try:
            logger.info("Running VLM stage for camera=%s, video=%s", job.camera_id, job.video_path)

            if not job.video_path:
                raise VlmInvalidRequestError("stage request is missing video_path")

            temp_file_path = self._minio.download_video_to_temp(
                job.video_path, bucket_name=job.bucket_name
            )
            return self._classify(temp_file_path)
        except (VlmInvalidRequestError, MinioObjectNotFoundError):
            raise
        except Exception:
            logger.error("Error during VLM classification stage", exc_info=True)
            raise
        finally:
            if temp_file_path:
                self._minio.cleanup_temp_file(temp_file_path)

    def _classify(self, video_path: str) -> VlmStageResult:
        frames, effective_fps = self._frames.extract(video_path)
        last_error_msg: str = ""

        for attempt in range(self._settings.max_retries + 1):
            try:
                logger.info(
                    "Analyzing video %s (attempt %s/%s)",
                    video_path,
                    attempt + 1,
                    self._settings.max_retries + 1,
                )
                raw_text = self._model.generate(frames, effective_fps)
                logger.info("VLM raw output: %s", raw_text)
                result = self._mapper.map(raw_text)
                logger.info("VLM classification result: event_type=%s", result.event_type)
                return result
            except Exception as e:
                if isinstance(e, VlmInvalidJsonError) and not self._settings.do_sample:
                    logger.error(
                        "VLM returned invalid JSON with greedy decoding; not retrying: %s",
                        e,
                    )
                    return self._unknown_result(f"Failed to parse VLM output as JSON: {e}")
                last_error_msg = str(e)
                logger.error("VLM analysis failed: %s", e, exc_info=True)
                if e.__traceback__ is not None:
                    traceback.clear_frames(e.__traceback__)
                del e
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                if attempt < self._settings.max_retries:
                    logger.info("Retrying in %s seconds...", self._settings.retry_delay_seconds)
                    time.sleep(self._settings.retry_delay_seconds)

        return self._unknown_result(
            f"Failed to analyze video after retries: {last_error_msg}"
        )

    def _unknown_result(self, reason: str) -> VlmStageResult:
        logger.error(
            "Publishing VLM stage as %s so the pipeline can complete: %s",
            self._settings.unknown_event_type,
            reason,
        )
        return VlmStageResult(
            event_type=self._settings.unknown_event_type,
            description=reason,
        )
