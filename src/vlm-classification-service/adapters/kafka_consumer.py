import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Callable

from confluent_kafka import KafkaError, Producer
from kafka import KafkaConsumer
from kafka.errors import CommitFailedError

from config.kafka import KafkaSettings

logger = logging.getLogger(__name__)


class ConsumerFatalError(Exception):
    """Unrecoverable consumer error; service should exit with non-zero code."""


class PoisonMessageError(ValueError):
    """Message payload cannot be processed; send to DLQ without retrying inference."""

    retryable = False


class VideoConsumer:
    """Kafka consumer for VLM stage requests."""

    def __init__(self, settings: KafkaSettings):
        self._settings = settings
        self.consumer = None
        self.dlq_producer = None
        self.running = False
        self.retry_counts: dict[tuple[str, int, int], int] = {}
        self._dlq_flush_timeout = settings.kafka_dlq_producer_flush_timeout_seconds

    def connect(self):
        try:
            self.consumer = KafkaConsumer(
                self._settings.kafka_topic,
                bootstrap_servers=self._settings.kafka_bootstrap_servers.split(","),
                group_id=self._settings.kafka_group_id,
                auto_offset_reset=self._settings.kafka_consumer_auto_offset_reset,
                enable_auto_commit=False,
                max_poll_records=self._settings.kafka_max_poll_records,
                max_poll_interval_ms=self._settings.kafka_max_poll_interval_ms,
                session_timeout_ms=self._settings.kafka_session_timeout_ms,
                heartbeat_interval_ms=self._settings.kafka_heartbeat_interval_ms,
            )
            self.dlq_producer = Producer(
                self._settings.build_kafka_producer_config(
                    client_id=self._settings.kafka_dlq_producer_client_id
                )
            )
            logger.info("Connected to Kafka topic: %s", self._settings.kafka_topic)
            logger.info(
                "Kafka consumer config: max_poll_interval_ms=%sms, max_poll_records=%s, session_timeout_ms=%sms",
                self._settings.kafka_max_poll_interval_ms,
                self._settings.kafka_max_poll_records,
                self._settings.kafka_session_timeout_ms,
            )
            return True
        except Exception as e:
            logger.error("Failed to connect to Kafka: %s", e)
            return False

    def consume_videos(self, callback: Callable):
        """
        Consume stage requests one at a time.

        VLM inference runs synchronously in the poll thread. Heartbeats are
        sent by kafka-python's background thread; max_poll_interval_ms allows
        long-running jobs between poll() calls.
        """
        if not self.consumer and not self.connect():
            raise ConsumerFatalError("Cannot start consuming - connection failed")

        self.running = True
        logger.info("Starting to consume VLM stage requests...")

        try:
            while self.running:
                records = self.consumer.poll(
                    timeout_ms=self._settings.kafka_poll_timeout_ms,
                    max_records=self._settings.kafka_max_poll_records,
                )
                if not records:
                    continue

                for _, messages in records.items():
                    for message in messages:
                        if not self.running:
                            break
                        self._process_message(message, callback)
                    if not self.running:
                        break

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
        try:
            payload = self._parse_message_value(message)
        except PoisonMessageError as e:
            logger.error(
                "Invalid Kafka payload (topic=%s partition=%s offset=%s), sending to DLQ: %s",
                message.topic,
                message.partition,
                message.offset,
                e,
            )
            self._handoff_to_dlq_and_commit(message, e, attempts=1)
            return

        logger.info(
            "Received stage request for camera %s "
            "(topic=%s partition=%s offset=%s)",
            payload.get("camera_id", "unknown"),
            message.topic,
            message.partition,
            message.offset,
        )

        retry_key = (message.topic, message.partition, message.offset)
        while self.running:
            try:
                callback(payload)
                self._commit_message()
                self.retry_counts.pop(retry_key, None)
                return
            except ConsumerFatalError:
                raise
            except Exception as e:
                retryable = getattr(e, "retryable", True)
                attempts = self.retry_counts.get(retry_key, 0) + 1
                self.retry_counts[retry_key] = attempts

                if not retryable or attempts >= self._settings.kafka_processing_max_retries:
                    if not retryable:
                        logger.error(
                            "Non-retryable processing error, sending to DLQ and committing offset: %s",
                            e,
                        )
                    else:
                        logger.error(
                            "Message failed after %s retries, sending to DLQ and committing offset",
                            attempts,
                        )
                    self._handoff_to_dlq_and_commit(
                        message, e, attempts, value=payload
                    )
                    self.retry_counts.pop(retry_key, None)
                    return

                logger.warning(
                    "Message processing failed (attempt %s/%s), retrying after %.1fs: %s",
                    attempts,
                    self._settings.kafka_processing_max_retries,
                    self._settings.kafka_processing_retry_backoff_seconds,
                    e,
                )
                time.sleep(self._settings.kafka_processing_retry_backoff_seconds)

        logger.info(
            "Consumer stopped while processing topic=%s partition=%s offset=%s; "
            "offset will not be committed",
            message.topic,
            message.partition,
            message.offset,
        )

    def _commit_message(self) -> None:
        for attempt in range(2):
            try:
                self.consumer.commit()
                return
            except CommitFailedError as e:
                if attempt == 0:
                    logger.warning("Commit failed, polling to rejoin group before retry: %s", e)
                    self.consumer.poll(timeout_ms=self._settings.kafka_poll_timeout_ms)
                else:
                    raise ConsumerFatalError("Failed to commit offset after processing") from e

    def close(self):
        self.running = False
        if self.consumer:
            logger.info("Closing Kafka consumer...")
            self.consumer.close()
            self.consumer = None
        if self.dlq_producer:
            self.dlq_producer.flush(timeout=self._dlq_flush_timeout)
            self.dlq_producer = None

    def stop(self):
        self.running = False

    @staticmethod
    def _parse_message_value(message) -> dict[str, Any]:
        raw = message.value
        if raw is None:
            raise PoisonMessageError("Kafka message value is empty")
        if isinstance(raw, bytes):
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as e:
                raise PoisonMessageError("Kafka message value is not valid UTF-8") from e
        elif isinstance(raw, str):
            text = raw
        elif isinstance(raw, dict):
            return raw
        else:
            raise PoisonMessageError(
                f"Unsupported Kafka message value type: {type(raw).__name__}"
            )

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as e:
            raise PoisonMessageError("Kafka message value is not valid JSON") from e
        if not isinstance(parsed, dict):
            raise PoisonMessageError("Kafka message JSON must be an object")
        return parsed

    @staticmethod
    def _dlq_value(message, parsed: dict[str, Any] | None) -> Any:
        if parsed is not None:
            return parsed
        raw = message.value
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return raw

    def _handoff_to_dlq_and_commit(
        self,
        message,
        error: Exception,
        attempts: int,
        value: dict[str, Any] | None = None,
    ) -> None:
        try:
            self._send_to_dlq(message, error, attempts, value=value)
        except ConsumerFatalError:
            raise
        except Exception as dlq_error:
            raise ConsumerFatalError(
                "Failed to send message to DLQ; offset will not be committed"
            ) from dlq_error
        self._commit_message()

    def _send_to_dlq(
        self,
        message,
        error: Exception,
        attempts: int,
        value: dict[str, Any] | None = None,
    ) -> None:
        if not self.dlq_producer or not self._settings.kafka_dlq_topic:
            raise ConsumerFatalError(
                "Cannot send to DLQ: producer or topic is not configured"
            )

        payload = {
            "source_topic": message.topic,
            "partition": message.partition,
            "offset": message.offset,
            "key": message.key.decode("utf-8", errors="ignore") if message.key else None,
            "value": self._dlq_value(message, value),
            "error": str(error),
            "attempts": attempts,
            "failed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        encoded = json.dumps(payload).encode("utf-8")
        delivery_error: list[KafkaError | str] = []

        def on_delivery(err, _msg):
            if err is not None:
                delivery_error.append(err)

        self.dlq_producer.produce(
            topic=self._settings.kafka_dlq_topic,
            value=encoded,
            callback=on_delivery,
        )
        remaining = self.dlq_producer.flush(timeout=self._dlq_flush_timeout)
        if remaining > 0:
            raise RuntimeError(
                f"DLQ flush timed out with {remaining} message(s) still in queue"
            )
        if delivery_error:
            raise RuntimeError(f"DLQ delivery failed: {delivery_error[0]}")
