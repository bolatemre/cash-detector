import logging
import os
from typing import Dict, Any
from datetime import datetime
from services.kafka_producer import ClassificationKafkaProducer
from services.minio_service import MinioService
from services.run_yolo7 import YOLOv7ActionClassifier
from config.settings import settings

logger = logging.getLogger(__name__)


class ClassificationService:
    """Service for classifying uploaded videos"""
    
    def __init__(self, kafka_producer: ClassificationKafkaProducer | None = None):
        self.logger = logger
        self.kafka_producer = kafka_producer
        self.minio_service = MinioService()
        
        # Initialize the action classifier (mandatory - service won't work without it)
        self.action_classifier = YOLOv7ActionClassifier()
        self.logger.info("ActionClassifier initialized successfully")
        
    def process_video(self, video_data: Dict[str, Any]) -> None:
        """
        Process uploaded video for classification
        
        Args:
            video_data: Dictionary containing video information
                - camera_id: Camera identifier
                - video_path: Path to video in MinIO
                - bucket_name: MinIO bucket name
                - event_type: Type of event (should be 'video_uploaded')
        """
        result = self.classify_video_payload(video_data)
        camera_id = video_data.get('camera_id')
        video_path = video_data.get('video_path')
        bucket_name = video_data.get('bucket_name')
        recording_started_at = video_data.get('recording_started_at')
        self._send_classification_event(
            camera_id=camera_id,
            event_type=result["event_type"],
            video_path=video_path,
            bucket_name=bucket_name,
            detected_at=recording_started_at
        )
        self.logger.info(f"Video classification processing completed: {result['event_type']}")

    def classify_video_payload(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Classify uploaded video and return stage result without publishing Kafka event.

        Returns:
            Dict[str, Any]: stage result with required field "event_type"
        """
        temp_file_path = None
        try:
            camera_id = video_data.get('camera_id')
            video_path = video_data.get('video_path')
            bucket_name = video_data.get('bucket_name')
            self.logger.info(f"Running classification stage for camera={camera_id}, video={video_path}")

            temp_file_path = self.minio_service.download_video_to_temp(video_path, bucket_name=bucket_name)
            if not temp_file_path:
                raise RuntimeError(f"Failed to download video from MinIO: {video_path}")

            result = self.action_classifier.classify_video(temp_file_path)
            class_name = result.get('class_name', 'error')
            return {
                "event_type": class_name,
                "confidence": result.get("confidence", 0.0),
                "predicted_class": result.get("predicted_class", -1),
                "features_collected": result.get("features_collected", 0),
            }
        except Exception as e:
            self.logger.error(f"Error during classification stage: {e}", exc_info=True)
            raise
        finally:
            if temp_file_path:
                self.minio_service.cleanup_temp_file(temp_file_path)
    
    def _classify_video(self, video_file_path: str) -> str:
        """
        Classify video using ActionClassifier
        
        Args:
            video_file_path: Path to downloaded video file
            
        Returns:
            str: Classification result ('cash_register' | 'suspicious' | 'change')
        """
        try:
            result = self.action_classifier.classify_video(video_file_path)
            
            class_name = result.get('class_name', 'unknown')
            confidence = result.get('confidence', 0.0)
            features_collected = result.get('features_collected', 0)
            
            self.logger.info(
                f"Video classification result: {class_name} "
                f"(confidence: {confidence:.2f}, features: {features_collected})"
            )
            
            return class_name
            
        except Exception as e:
            self.logger.error(f"Error during video classification: {e}", exc_info=True)
            # Return 'error' as default in case of error to avoid false alerts
            return "error"
    
    def _send_classification_event(self, camera_id: str, event_type: str, video_path: str, bucket_name: str, detected_at: str = None) -> bool:
        """
        Send classification event to Kafka for event-processor to consume
        
        Args:
            camera_id: Camera identifier
            event_type: Classification result ('suspicious' or 'normal')
            video_path: Path to video in MinIO
            bucket_name: MinIO bucket name
            
        Returns:
            bool: True if event was sent successfully
        """
        try:
            # Construct full video URL using configurable MinIO URL
            video_url = f"{settings.minio_endpoint}/{bucket_name}/{video_path}"
            
            # Send event to Kafka
            if not self.kafka_producer:
                self.logger.error("Kafka producer not configured; cannot send classification event")
                return False
            success = self.kafka_producer.send_classification_event(
                camera_id=camera_id,
                event_type=event_type,
                video_url=video_url,
                detected_at=detected_at or datetime.utcnow().isoformat() + "Z",
            )
            
            if success:
                self.logger.info(f"Classification event sent to Kafka: {event_type} for camera {camera_id}")
            else:
                self.logger.error(f"Failed to send classification event to Kafka for camera {camera_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error sending classification event: {e}", exc_info=True)
            return False
