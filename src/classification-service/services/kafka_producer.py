import logging
from datetime import datetime
from typing import Optional

from common.confluent_kafka_producer import ConfluentKafkaProducer
from common.kafka_messages import PipelineStageEnvelope, SecurityEventMessage
from config.settings import settings

logger = logging.getLogger(__name__)


def _delivery_callback(err, msg) -> None:
    if err:
        logger.error("Message delivery failed: %s", err)
    else:
        logger.info(
            "Message delivered to %s [%s] at offset %s",
            msg.topic(),
            msg.partition(),
            msg.offset(),
        )


class ClassificationKafkaProducer(ConfluentKafkaProducer):
    def __init__(self) -> None:
        super().__init__(settings)

    def send_classification_event(
        self,
        camera_id: str,
        event_type: str,
        video_url: Optional[str] = None,
        detected_at: Optional[str] = None,
    ) -> bool:
        detected = detected_at or datetime.utcnow().isoformat() + "Z"
        message = SecurityEventMessage(
            event_type=event_type,
            camera_id=camera_id,
            detected_at=detected,
            video_url=video_url,
        )
        return self.produce_json(
            settings.kafka_security_events_topic,
            message.model_dump(mode="json"),
            callback=_delivery_callback,
        )

    def send_stage_result(self, payload: PipelineStageEnvelope) -> bool:
        return self.produce_json(
            settings.kafka_stage_results_topic,
            payload.model_dump(mode="json"),
            callback=_delivery_callback,
        )
