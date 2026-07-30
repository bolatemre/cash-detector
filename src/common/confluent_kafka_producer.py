import json
import logging
from typing import Any, Callable, Optional

from confluent_kafka import Producer

from common.kafka_producer_config import KafkaProducerConfigMixin

logger = logging.getLogger(__name__)

DeliveryCallback = Optional[Callable]


class ConfluentKafkaProducer:
    def __init__(self, settings: KafkaProducerConfigMixin, *, client_id: str | None = None) -> None:
        self._settings = settings
        self._flush_timeout = settings.kafka_producer_flush_timeout_seconds
        self._producer = Producer(settings.build_kafka_producer_config(client_id=client_id))

    def close(self, timeout: float | None = None) -> None:
        self._producer.flush(timeout=timeout if timeout is not None else self._flush_timeout)

    def produce_json(
        self,
        topic: str,
        payload: dict[str, Any],
        *,
        callback: DeliveryCallback = None,
    ) -> bool:
        try:
            self._producer.produce(
                topic=topic,
                value=json.dumps(payload).encode("utf-8"),
                callback=callback,
            )
            self._producer.flush(timeout=self._flush_timeout)
            return True
        except Exception as e:
            logger.error("Error producing to topic %s: %s", topic, e, exc_info=True)
            return False
