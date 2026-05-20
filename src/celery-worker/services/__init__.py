"""Services package for celery worker"""

from .camera_service import target_recording, CameraConnectionLostError
from .minio_service import (
    get_minio_client,
    upload_video_to_minio
)
from .kafka_producer import (
    CeleryKafkaProducer,
    get_kafka_producer,
    send_video_uploaded_event,
)

__all__ = [
    'target_recording',
    'CameraConnectionLostError',
    'get_minio_client',
    'upload_video_to_minio',
    'CeleryKafkaProducer',
    'get_kafka_producer',
    'send_video_uploaded_event',
]

