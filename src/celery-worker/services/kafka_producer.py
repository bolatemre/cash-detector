import logging

from common.confluent_kafka_producer import ConfluentKafkaProducer
from common.kafka_messages import VideoUploadedMessage
from config.settings import settings

logger = logging.getLogger(__name__)

_producer: "CeleryKafkaProducer | None" = None


def get_kafka_producer() -> "CeleryKafkaProducer":
    global _producer
    if _producer is None:
        _producer = CeleryKafkaProducer()
    return _producer


class CeleryKafkaProducer(ConfluentKafkaProducer):
    def __init__(self) -> None:
        super().__init__(settings)

    def send_video_uploaded_event(
        self,
        camera_id: str,
        video_path: str,
        bucket_name: str | None = None,
        recording_started_at: str | None = None,
    ) -> bool:
        message = VideoUploadedMessage(
            camera_id=camera_id,
            video_path=video_path,
            bucket_name=bucket_name,
            recording_started_at=recording_started_at,
        )
        return self.produce_json(
            settings.kafka_uploaded_videos_topic,
            message.model_dump(mode="json"),
        )


def send_video_uploaded_event(
    camera_id: str,
    video_path: str,
    bucket_name: str | None = None,
    recording_started_at: str | None = None,
) -> bool:
    return get_kafka_producer().send_video_uploaded_event(
        camera_id=camera_id,
        video_path=video_path,
        bucket_name=bucket_name,
        recording_started_at=recording_started_at,
    )
