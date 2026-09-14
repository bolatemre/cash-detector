import logging
import signal
import sys

from common.kafka_messages import PipelineStageEnvelope, StageName

from kafka_consumer import VideoConsumer
from kafka_producer import TrackingKafkaProducer
from config.settings import settings
from tracking_stage_service import TrackingStageService

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)
consumer_instance: VideoConsumer | None = None
kafka_producer_instance: TrackingKafkaProducer | None = None


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
        kafka_producer_instance = TrackingKafkaProducer()
        tracking_service = TrackingStageService()

        def process_video_callback(video_data: dict):
            job = PipelineStageEnvelope.model_validate(video_data)
            stage_result = tracking_service.process(job.model_dump(mode="json"))
            completion = job.with_completion(StageName.TRACKING, stage_result)
            sent = kafka_producer_instance.send_stage_result(completion)
            if not sent:
                raise RuntimeError("Failed to send tracking stage result")

        consumer_instance.consume_videos(process_video_callback)
    except Exception as e:
        logger.error("Fatal error in tracking service: %s", e, exc_info=True)
        sys.exit(1)
    finally:
        if consumer_instance:
            consumer_instance.close()
        if kafka_producer_instance:
            kafka_producer_instance.close()
        logger.info("Tracking service stopped")


if __name__ == "__main__":
    main()
