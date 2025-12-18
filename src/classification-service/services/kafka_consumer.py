import json
import logging
from kafka import KafkaConsumer
from kafka.errors import KafkaError
from typing import Callable
from config.settings import settings

logger = logging.getLogger(__name__)


class VideoConsumer:
    """Kafka consumer for receiving uploaded video events"""
    
    def __init__(self):
        self.consumer = None
        self.running = False
        
    def connect(self):
        """Establish connection to Kafka"""
        try:
            self.consumer = KafkaConsumer(
                settings.kafka_topic,
                bootstrap_servers=settings.kafka_bootstrap_servers.split(','),
                group_id=settings.kafka_group_id,
                auto_offset_reset='earliest',
                enable_auto_commit=False,  # Manual commit to ensure messages are only committed after successful processing
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                max_poll_records=settings.kafka_max_poll_records,  # Process one at a time to avoid timeout
                max_poll_interval_ms=settings.kafka_max_poll_interval_ms,  # Allow up to 15 minutes for video processing
                session_timeout_ms=settings.kafka_session_timeout_ms,
                heartbeat_interval_ms=settings.kafka_heartbeat_interval_ms
            )
            logger.info(f"Connected to Kafka topic: {settings.kafka_topic}")
            logger.info(f"Kafka consumer config: max_poll_interval_ms={settings.kafka_max_poll_interval_ms}ms, "
                       f"max_poll_records={settings.kafka_max_poll_records}, "
                       f"session_timeout_ms={settings.kafka_session_timeout_ms}ms")
            return True
        except KafkaError as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            return False
    
    def consume_videos(self, callback: Callable):
        """
        Consume video upload events from Kafka and process them using callback
        
        Args:
            callback: Function to process each video upload message
        """
        if not self.consumer:
            if not self.connect():
                logger.error("Cannot start consuming - connection failed")
                return
        
        self.running = True
        logger.info("Starting to consume video upload events...")
        
        try:
            for message in self.consumer:
                if not self.running:
                    break
                
                try:
                    video_data = message.value
                    logger.info(f"Received video upload event: {video_data.get('event_type', 'unknown')} "
                              f"from camera {video_data.get('camera_id', 'unknown')}")
                    
                    # Process the video using callback
                    # This may take a long time (downloading, ML classification, etc.)
                    callback(video_data)
                    
                    # Commit offset only after successful processing
                    # This ensures we don't lose messages if processing fails
                    self.consumer.commit()
                    logger.debug(f"Committed offset for message from camera {video_data.get('camera_id', 'unknown')}")
                    
                except Exception as e:
                    logger.error(f"Error processing message: {e}", exc_info=True)
                    # Don't commit on error - message will be retried
                    # Continue processing other messages
                    
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Error in consumer loop: {e}", exc_info=True)
        finally:
            self.close()
    
    def close(self):
        """Close Kafka consumer connection"""
        self.running = False
        if self.consumer:
            logger.info("Closing Kafka consumer...")
            self.consumer.close()
            self.consumer = None
    
    def stop(self):
        """Stop consuming events"""
        self.running = False
