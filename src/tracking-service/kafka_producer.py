import logging

from common.confluent_kafka_producer import ConfluentKafkaProducer
from common.kafka_messages import PipelineStageEnvelope
from config.settings import settings

logger = logging.getLogger(__name__)


class TrackingKafkaProducer(ConfluentKafkaProducer):
    def __init__(self) -> None:
        super().__init__(settings)

    def send_stage_result(self, payload: PipelineStageEnvelope) -> bool:
        return self.produce_json(settings.kafka_stage_results_topic, payload.model_dump(mode="json"))
