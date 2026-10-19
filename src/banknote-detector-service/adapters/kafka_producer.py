from common.confluent_kafka_producer import ConfluentKafkaProducer
from common.kafka_messages import PipelineStageEnvelope
from config.kafka import KafkaSettings


class BanknoteKafkaProducer(ConfluentKafkaProducer):
    def __init__(self, settings: KafkaSettings) -> None:
        super().__init__(settings)
        self._stage_results_topic = settings.kafka_stage_results_topic

    def send_stage_result(self, payload: PipelineStageEnvelope) -> bool:
        return self.produce_json(
            self._stage_results_topic,
            payload.model_dump(mode="json"),
        )
