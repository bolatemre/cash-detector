import json
import logging
import time
from datetime import datetime
from typing import Callable

from confluent_kafka import Producer
from kafka import KafkaConsumer
from config.settings import settings

logger = logging.getLogger(__name__)


class VideoConsumer:
    """Kafka consumer for receiving uploaded video events"""
    
    def __init__(self):
        self.consumer = None
        self.dlq_producer = None
        self.running = False
        self.retry_counts: dict[tuple[str, int, int], int] = {}
        self._dlq_flush_timeout = settings.kafka_dlq_producer_flush_timeout_seconds
        
    def connect(self):
        """Establish connection to Kafka"""
        try:
            self.consumer = KafkaConsumer(
                settings.kafka_topic,
                bootstrap_servers=settings.kafka_bootstrap_servers.split(','),
                group_id=settings.kafka_group_id,
                auto_offset_reset=settings.kafka_consumer_auto_offset_reset,
                enable_auto_commit=False,  # Manual commit to ensure messages are only committed after successful processing
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                max_poll_records=settings.kafka_max_poll_records,  # Process one at a time to avoid timeout
                max_poll_interval_ms=settings.kafka_max_poll_interval_ms,  # Allow up to 15 minutes for video processing
                session_timeout_ms=settings.kafka_session_timeout_ms,
                heartbeat_interval_ms=settings.kafka_heartbeat_interval_ms
            )
            self.dlq_producer = Producer(
                settings.build_kafka_producer_config(client_id=settings.kafka_dlq_producer_client_id)
            )
            logger.info(f"Connected to Kafka topic: {settings.kafka_topic}")
            logger.info(f"Kafka consumer config: max_poll_interval_ms={settings.kafka_max_poll_interval_ms}ms, "
                       f"max_poll_records={settings.kafka_max_poll_records}, "
                       f"session_timeout_ms={settings.kafka_session_timeout_ms}ms")
            return True
        except Exception as e:
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
            while self.running:
                records = self.consumer.poll(
                    timeout_ms=settings.kafka_poll_timeout_ms,
                    max_records=settings.kafka_max_poll_records,
                )
                if not records:
                    continue

                for _, messages in records.items():
                    for message in messages:
                        if not self.running:
                            break

                        retry_key = (message.topic, message.partition, message.offset)
                        try:
                            video_data = message.value
                            logger.info(
                                f"Received stage request: {video_data.get('event_type', 'unknown')} "
                                f"from camera {video_data.get('camera_id', 'unknown')}"
                            )
                            callback(video_data)
                            self.consumer.commit()
                            self.retry_counts.pop(retry_key, None)
                        except Exception as e:
                            attempts = self.retry_counts.get(retry_key, 0) + 1
                            self.retry_counts[retry_key] = attempts
                            if attempts >= settings.kafka_processing_max_retries:
                                logger.error(
                                    "Message failed after %s retries, sending to DLQ and committing offset",
                                    attempts,
                                )
                                self._send_to_dlq(message, e, attempts)
                                self.consumer.commit()
                                self.retry_counts.pop(retry_key, None)
                            else:
                                logger.warning(
                                    "Message processing failed (attempt %s/%s), retrying after %.1fs: %s",
                                    attempts,
                                    settings.kafka_processing_max_retries,
                                    settings.kafka_processing_retry_backoff_seconds,
                                    e,
                                )
                                time.sleep(settings.kafka_processing_retry_backoff_seconds)

        except SystemExit:
            logger.info("Shutdown signal received, stopping consumer loop")
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
        if self.dlq_producer:
            self.dlq_producer.flush(timeout=self._dlq_flush_timeout)
            self.dlq_producer = None
    
    def stop(self):
        """Stop consuming events"""
        self.running = False

    def _send_to_dlq(self, message, error: Exception, attempts: int) -> None:
        if not self.dlq_producer or not settings.kafka_dlq_topic:
            return
        payload = {
            "source_topic": message.topic,
            "partition": message.partition,
            "offset": message.offset,
            "key": message.key.decode("utf-8", errors="ignore") if message.key else None,
            "value": message.value,
            "error": str(error),
            "attempts": attempts,
            "failed_at": datetime.utcnow().isoformat() + "Z",
        }
        self.dlq_producer.produce(
            topic=settings.kafka_dlq_topic,
            value=json.dumps(payload).encode("utf-8"),
        )
        self.dlq_producer.flush(timeout=self._dlq_flush_timeout)
