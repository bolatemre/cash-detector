import logging
from datetime import datetime
from typing import Optional

from common.confluent_kafka_producer import ConfluentKafkaProducer
from common.kafka_messages import PipelineStageEnvelope, SecurityEventMessage
from pipeline_settings import settings

logger = logging.getLogger(__name__)


class PipelineKafkaProducer(ConfluentKafkaProducer):
    def __init__(self) -> None:
        super().__init__(settings)

    def send_security_event(
        self,
        camera_id: Optional[str],
        event_type: str,
        video_url: Optional[str] = None,
        detected_at: Optional[str] = None,
    ) -> bool:
        detected = detected_at or datetime.utcnow().isoformat() + "Z"
        message = SecurityEventMessage(
            event_type=event_type,
            camera_id=camera_id or "",
            detected_at=detected,
            video_url=video_url,
        )
        return self.produce_json(
            settings.kafka_security_events_topic,
            message.model_dump(mode="json"),
        )

    def send_stage_request(self, topic: str, payload: PipelineStageEnvelope) -> bool:
        return self.produce_json(topic, payload.model_dump(mode="json"))
