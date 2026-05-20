import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from common.kafka_messages import PipelineStageEnvelope, StageName, VideoUploadedMessage
from kafka_producer import PipelineKafkaProducer
from pipeline_settings import settings
from services.minio_service import MinioService

logger = logging.getLogger(__name__)

_STAGE_TOPICS: dict[str, str] = {
    "classification": settings.kafka_classification_requests_topic,
    "tracking": settings.kafka_tracking_requests_topic,
}


class PipelineService:
    def __init__(self, kafka_producer: PipelineKafkaProducer, minio_service: MinioService | None = None):
        self.kafka_producer = kafka_producer
        self.minio_service = minio_service or MinioService()
        self.alert_labels = {label.strip().lower() for label in settings.alert_labels.split(",") if label.strip()}
        self.stage_order = [stage.strip().lower() for stage in settings.stage_order.split(",") if stage.strip()]
        self._validate_stage_order()

    def _validate_stage_order(self) -> None:
        if sorted(self.stage_order) != sorted(_STAGE_TOPICS):
            raise ValueError(f"STAGE_ORDER must contain exactly: {sorted(_STAGE_TOPICS)}")

    def handle_uploaded_video(self, video_data: dict[str, Any]) -> None:
        uploaded = VideoUploadedMessage.model_validate(video_data)
        correlation_id = str(uuid.uuid4())
        first_stage = self.stage_order[0]

        envelope = PipelineStageEnvelope.start(
            correlation_id=correlation_id,
            camera_id=uploaded.camera_id,
            video_path=uploaded.video_path,
            bucket_name=uploaded.bucket_name or settings.minio_bucket,
            recording_started_at=uploaded.recording_started_at or _utc_now_iso(),
            stage_order=list(self.stage_order),
        )
        self._send_to_stage(first_stage, envelope)

        logger.info(
            "Queued first stage '%s' for correlation_id=%s camera=%s",
            first_stage,
            correlation_id,
            envelope.camera_id,
        )

    def handle_stage_result(self, event_data: dict[str, Any]) -> None:
        envelope = PipelineStageEnvelope.model_validate(event_data)
        try:
            stage_name, _ = envelope.require_completion()
            event_type = envelope.completion_event_type()
        except ValueError as e:
            raise RuntimeError(f"Invalid stage completion: {e}: {event_data}") from e

        stage_results = envelope.merged_stage_results()

        if stage_name in stage_results:
            logger.info(
                "Applying MinIO tags after stage '%s' correlation_id=%s camera=%s video=%s",
                stage_name,
                envelope.correlation_id,
                envelope.camera_id,
                envelope.video_path,
            )
            self._tag_stage_on_video(envelope, stage_name, stage_results[stage_name])

        if self._is_alert(event_type) and envelope.has_next_stage():
            next_stage = envelope.next_stage()
            assert next_stage is not None
            next_envelope = envelope.for_next_stage(stage_results)
            self._send_to_stage(next_stage, next_envelope)
            logger.info(
                "Alert from stage '%s' -> queued next stage '%s' for correlation_id=%s",
                stage_name,
                next_stage,
                envelope.correlation_id,
            )
            return

        bucket_name = envelope.bucket_name or settings.minio_bucket
        video_url = f"{settings.minio_public_url}/{bucket_name}/{envelope.video_path}"
        detected_at = envelope.recording_started_at or _utc_now_iso()

        success = self.kafka_producer.send_security_event(
            camera_id=envelope.camera_id,
            event_type=event_type,
            video_url=video_url,
            detected_at=detected_at,
        )
        if not success:
            logger.error("Failed to publish final pipeline event")
            return

        logger.info(
            "Pipeline completed correlation_id=%s final_event=%s stage_results=%s",
            envelope.correlation_id,
            event_type,
            stage_results,
        )

    def _is_alert(self, event_type: str) -> bool:
        return (event_type or "").lower() in self.alert_labels

    def _tag_stage_on_video(
        self,
        envelope: PipelineStageEnvelope,
        stage_name: StageName,
        stage_result: dict[str, Any],
    ) -> None:
        if not envelope.video_path:
            logger.warning(
                "Cannot tag %s: missing video_path correlation_id=%s",
                stage_name,
                envelope.correlation_id,
            )
            return
        bucket_name = envelope.bucket_name or settings.minio_bucket
        logger.debug(
            "MinIO tag request stage=%s bucket=%s path=%s result=%s",
            stage_name,
            bucket_name,
            envelope.video_path,
            stage_result,
        )
        if not self.minio_service.tag_video_with_stage_result(
            video_path=envelope.video_path,
            stage_name=stage_name,
            stage_result=stage_result,
            bucket_name=bucket_name,
        ):
            logger.warning(
                "Failed to tag video with %s correlation_id=%s bucket=%s path=%s",
                stage_name,
                envelope.correlation_id,
                bucket_name,
                envelope.video_path,
            )
            return
        logger.info(
            "MinIO tags applied for stage '%s' correlation_id=%s bucket=%s path=%s",
            stage_name,
            envelope.correlation_id,
            bucket_name,
            envelope.video_path,
        )

    def _send_to_stage(self, stage_name: str, payload: PipelineStageEnvelope) -> None:
        topic = _STAGE_TOPICS.get(stage_name)
        if topic is None:
            raise ValueError(f"Unsupported stage: {stage_name!r}")
        if not self.kafka_producer.send_stage_request(topic=topic, payload=payload):
            raise RuntimeError(f"Failed to send stage request for '{stage_name}'")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
