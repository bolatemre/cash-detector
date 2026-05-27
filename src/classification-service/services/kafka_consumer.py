import json
import logging
import time
from datetime import datetime
from typing import Callable

from confluent_kafka import Producer
from kafka import KafkaConsumer
from kafka.errors import CommitFailedError

from config.settings import settings

logger = logging.getLogger(__name__)


class ConsumerFatalError(Exception):
    """Unrecoverable consumer error; service should exit with non-zero code."""


class VideoConsumer:
    """Kafka consumer for receiving uploaded video events."""

    def __init__(self):
        self.consumer = None
        self.dlq_producer = None
        self.running = False
        self.retry_counts: dict[tuple[str, int, int], int] = {}
        self._dlq_flush_timeout = settings.kafka_dlq_producer_flush_timeout_seconds

    def connect(self):
        """Establish connection to Kafka."""
        try:
            self.consumer = KafkaConsumer(
                settings.kafka_topic,
                bootstrap_servers=settings.kafka_bootstrap_servers.split(","),
                group_id=settings.kafka_group_id,
                auto_offset_reset=settings.kafka_consumer_auto_offset_reset,
                enable_auto_commit=False,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                max_poll_records=settings.kafka_max_poll_records,
                max_poll_interval_ms=settings.kafka_max_poll_interval_ms,
                session_timeout_ms=settings.kafka_session_timeout_ms,
                heartbeat_interval_ms=settings.kafka_heartbeat_interval_ms,
            )
            self.dlq_producer = Producer(
                settings.build_kafka_producer_config(client_id=settings.kafka_dlq_producer_client_id)
            )
            logger.info("Connected to Kafka topic: %s", settings.kafka_topic)
            logger.info(
                "Kafka consumer config: max_poll_interval_ms=%sms, max_poll_records=%s, session_timeout_ms=%sms",
                settings.kafka_max_poll_interval_ms,
                settings.kafka_max_poll_records,
                settings.kafka_session_timeout_ms,
            )
            return True
        except Exception as e:
            logger.error("Failed to connect to Kafka: %s", e)
            return False

    def consume_videos(self, callback: Callable):
        """
        Consume video upload events one at a time.

        Classification runs synchronously in the poll thread. Heartbeats are
        sent by kafka-python's background thread; max_poll_interval_ms allows
        long-running jobs between poll() calls.
        """
        if not self.consumer and not self.connect():
            raise ConsumerFatalError("Cannot start consuming - connection failed")

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

                        video_data = message.value
                        logger.info(
                            "Received stage request: %s from camera %s "
                            "(topic=%s partition=%s offset=%s)",
                            video_data.get("event_type", "unknown"),
                            video_data.get("camera_id", "unknown"),
                            message.topic,
                            message.partition,
                            message.offset,
                        )
                        self._process_message(message, callback)

        except SystemExit:
            logger.info("Shutdown signal received, stopping consumer loop")
        except ConsumerFatalError:
            raise
        except Exception as e:
            logger.error("Error in consumer loop: %s", e, exc_info=True)
            raise ConsumerFatalError("Consumer loop terminated unexpectedly") from e
        finally:
            self.close()

    def _process_message(self, message, callback: Callable) -> None:
        retry_key = (message.topic, message.partition, message.offset)
        while self.running:
            try:
                callback(message.value)
                self._commit_message()
                self.retry_counts.pop(retry_key, None)
                return
            except Exception as e:
                attempts = self.retry_counts.get(retry_key, 0) + 1
                self.retry_counts[retry_key] = attempts

                if attempts >= settings.kafka_processing_max_retries:
                    logger.error(
                        "Message failed after %s retries, sending to DLQ and committing offset",
                        attempts,
                    )
                    self._send_to_dlq(message, e, attempts)
                    try:
                        self._commit_message()
                    except CommitFailedError as commit_error:
                        raise ConsumerFatalError(
                            "Failed to commit offset after DLQ handoff"
                        ) from commit_error
                    self.retry_counts.pop(retry_key, None)
                    return

                logger.warning(
                    "Message processing failed (attempt %s/%s), retrying after %.1fs: %s",
                    attempts,
                    settings.kafka_processing_max_retries,
                    settings.kafka_processing_retry_backoff_seconds,
                    e,
                )
                time.sleep(settings.kafka_processing_retry_backoff_seconds)

    def _commit_message(self) -> None:
        for attempt in range(2):
            try:
                self.consumer.commit()
                return
            except CommitFailedError as e:
                if attempt == 0:
                    logger.warning("Commit failed, polling to rejoin group before retry: %s", e)
                    self.consumer.poll(timeout_ms=settings.kafka_poll_timeout_ms)
                else:
                    raise ConsumerFatalError("Failed to commit offset after processing") from e

    def close(self):
        """Close Kafka consumer connection."""
        self.running = False
        if self.consumer:
            logger.info("Closing Kafka consumer...")
            self.consumer.close()
            self.consumer = None
        if self.dlq_producer:
            self.dlq_producer.flush(timeout=self._dlq_flush_timeout)
            self.dlq_producer = None

    def stop(self):
        """Stop consuming events."""
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
