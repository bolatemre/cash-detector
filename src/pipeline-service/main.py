import logging
import os
import signal
import sys
from typing import Optional

from kafka_consumer import VideoConsumer
from kafka_producer import PipelineKafkaProducer
from pipeline_service import PipelineService
from pipeline_settings import settings

log_handlers = [logging.StreamHandler(sys.stdout)]
try:
    os.makedirs("/app/logs", exist_ok=True)
    log_handlers.append(logging.FileHandler("/app/logs/pipeline-service.log"))
except OSError:
    pass

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=log_handlers,
)

logger = logging.getLogger(__name__)
consumer_instance: Optional[VideoConsumer] = None
kafka_producer_instance: Optional[PipelineKafkaProducer] = None


def signal_handler(signum, frame):
    logger.info("Received signal %s, shutting down...", signum)
    if consumer_instance:
        consumer_instance.stop()
    sys.exit(0)


def main():
    global consumer_instance, kafka_producer_instance
    logger.info("Starting %s v%s", settings.service_name, settings.service_version)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        consumer_instance = VideoConsumer()
        kafka_producer_instance = PipelineKafkaProducer()
        pipeline_service = PipelineService(kafka_producer_instance)

        def process_event_callback(topic, payload):
            if topic == settings.kafka_uploaded_videos_topic:
                pipeline_service.handle_uploaded_video(payload)
            elif topic == settings.kafka_stage_results_topic:
                pipeline_service.handle_stage_result(payload)
            else:
                logger.warning("Unknown topic %s, payload ignored", topic)

        consumer_instance.consume_events(process_event_callback)
    except Exception as e:
        logger.error("Fatal error in pipeline service: %s", e, exc_info=True)
        sys.exit(1)
    finally:
        if consumer_instance:
            consumer_instance.close()
        if kafka_producer_instance:
            kafka_producer_instance.close()
        logger.info("Pipeline service stopped")


if __name__ == "__main__":
    main()
