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
        self.classification_confidence_threshold = settings.classification_confidence_threshold
        self.unknown_label = settings.unknown_label
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

        decision = self._resolve_decision(envelope=envelope, stage_results=stage_results)
        if decision["action"] == "next":
            next_stage = decision["next_stage"]
            next_envelope = envelope.for_next_stage(stage_results)
            self._send_to_stage(next_stage, next_envelope)
            logger.info(
                "Queued next stage '%s' for correlation_id=%s (reason=%s)",
                next_stage,
                envelope.correlation_id,
                decision["reason"],
            )
            return

        event_type = decision["event_type"]

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
            "Pipeline completed correlation_id=%s final_event=%s reason=%s stage_results=%s",
            envelope.correlation_id,
            event_type,
            decision["reason"],
            stage_results,
        )

    def _resolve_decision(
        self,
        envelope: PipelineStageEnvelope,
        stage_results: dict[StageName, dict[str, Any]],
    ) -> dict[str, Any]:
        first_stage = envelope.stage_order[0]
        if first_stage == "classification":
            return self._resolve_classification_first_decision(envelope, stage_results)
        return self._resolve_tracking_first_decision(envelope, stage_results)

    def _resolve_classification_first_decision(
        self,
        envelope: PipelineStageEnvelope,
        stage_results: dict[StageName, dict[str, Any]],
    ) -> dict[str, Any]:
        classification = stage_results.get("classification")
        tracking = stage_results.get("tracking")

        if not classification:
            return self._final_event(envelope.completion_event_type(), "no_classification_payload")

        classification_class = self._classification_class(classification)
        confidence = self._classification_confidence(classification)

        if self._is_classification_unknown(classification, classification_class):
            return self._final_event(self.unknown_label, "classification_not_enough_frames")

        if tracking is None:
            if confidence > self.classification_confidence_threshold:
                reason = (
                    "classification_alert_high_confidence"
                    if classification_class == 1
                    else "classification_confident_normal"
                )
                return self._final_event(classification.get("event_type", self.unknown_label), reason)

            if confidence <= self.classification_confidence_threshold and envelope.has_next_stage():
                next_stage = envelope.next_stage()
                return self._next_stage(next_stage, "classification_low_confidence_requires_tracking")

            return self._final_event(classification.get("event_type", self.unknown_label), "classification_terminal_fallback")

        tracking_class = self._tracking_class(tracking)

        if confidence > self.classification_confidence_threshold and classification_class == 1 and tracking_class == 0:
            return self._final_event(classification.get("event_type", self.unknown_label), "classification_overrides_tracking")

        if confidence > self.classification_confidence_threshold and classification_class == 1 and tracking_class == 1:
            return self._final_event(classification.get("event_type", self.unknown_label), "consensus_alert")

        if confidence <= self.classification_confidence_threshold:
            if classification_class == tracking_class:
                return self._final_event(tracking.get("event_type", self.unknown_label), "consensus_low_confidence")
            return self._final_event(tracking.get("event_type", self.unknown_label), "tracking_overrides_low_confidence")

        return self._final_event(classification.get("event_type", self.unknown_label), "classification_terminal_fallback")

    def _resolve_tracking_first_decision(
        self,
        envelope: PipelineStageEnvelope,
        stage_results: dict[StageName, dict[str, Any]],
    ) -> dict[str, Any]:
        tracking = stage_results.get("tracking")
        classification = stage_results.get("classification")

        if not tracking:
            return self._final_event(envelope.completion_event_type(), "no_tracking_payload")

        tracking_class = self._tracking_class(tracking)

        if classification is None:
            if envelope.has_next_stage():
                next_stage = envelope.next_stage()
                return self._next_stage(next_stage, "tracking_completed_requires_classification")
            return self._final_event(tracking.get("event_type", self.unknown_label), "tracking_terminal_without_classification")

        classification_class = self._classification_class(classification)
        confidence = self._classification_confidence(classification)
        confidence_high = confidence > self.classification_confidence_threshold

        if self._is_classification_unknown(classification, classification_class):
            return self._final_event(self.unknown_label, "classification_not_enough_frames")

        if classification_class in (0, 2):
            if confidence_high:
                if tracking_class == 1:
                    return self._final_event(classification.get("event_type", self.unknown_label), "classification_overrides_alert_tracking")
                return self._final_event(classification.get("event_type", self.unknown_label), "consensus_normal_high_confidence")
            if tracking_class == 1:
                return self._final_event(tracking.get("event_type", self.unknown_label), "tracking_overrides_low_confidence")
            return self._final_event(classification.get("event_type", self.unknown_label), "consensus_normal_low_confidence")

        if classification_class == 1:
            if confidence_high:
                if tracking_class == 1:
                    return self._final_event(classification.get("event_type", self.unknown_label), "consensus_alert_high_confidence")
                return self._final_event(classification.get("event_type", self.unknown_label), "classification_overrides_tracking_high_confidence")
            if tracking_class == 1:
                return self._final_event(tracking.get("event_type", self.unknown_label), "tracking_alert_low_confidence")
            return self._final_event(tracking.get("event_type", self.unknown_label), "consensus_normal_low_confidence")

        return self._final_event(self.unknown_label, "unsupported_classification_class")

    def _classification_class(self, classification_result: dict[str, Any]) -> int:
        value = classification_result.get("predicted_class")
        if isinstance(value, bool):
            return -1
        if isinstance(value, int):
            return value
        try:
            return int(value)
        except (TypeError, ValueError):
            event_type = str(classification_result.get("event_type", "")).lower()
            if event_type in self.alert_labels:
                return 1
            if event_type == "change":
                return 2
            if event_type:
                return 0
            return -1

    def _classification_confidence(self, classification_result: dict[str, Any]) -> float:
        value = classification_result.get("confidence", 0.0)
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _tracking_class(self, tracking_result: dict[str, Any]) -> int:
        event_type = str(tracking_result.get("event_type", "")).lower()
        return 1 if self._is_alert(event_type) else 0

    def _is_classification_unknown(self, classification_result: dict[str, Any], classification_class: int) -> bool:
        event_type = str(classification_result.get("event_type", "")).lower()
        return event_type == self.unknown_label or classification_class not in (0, 1, 2)

    @staticmethod
    def _next_stage(next_stage: str | None, reason: str) -> dict[str, Any]:
        if not next_stage:
            return {"action": "final", "event_type": "unknown", "reason": "missing_next_stage"}
        return {"action": "next", "next_stage": next_stage, "reason": reason}

    @staticmethod
    def _final_event(event_type: str, reason: str) -> dict[str, Any]:
        return {"action": "final", "event_type": event_type, "reason": reason}

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
