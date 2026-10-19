import logging
import signal
import sys

from pydantic import ValidationError

from adapters.kafka_consumer import ConsumerFatalError, PoisonMessageError, VideoConsumer
from adapters.kafka_producer import BanknoteKafkaProducer
from common.kafka_messages import PipelineStageEnvelope, StageName
from config.settings import settings
from detection.service import BanknoteStageService

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)
consumer_instance: VideoConsumer | None = None
kafka_producer_instance: BanknoteKafkaProducer | None = None
_shutdown_requested = False


def signal_handler(signum, frame):
    global _shutdown_requested
    logger.info("Received signal %s, shutting down...", signum)
    _shutdown_requested = True
    if consumer_instance:
        consumer_instance.stop()


def main():
    global consumer_instance, kafka_producer_instance
    logger.info("Starting %s v%s", settings.service_name, settings.service_version)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    exit_code = 0
    try:
        logger.info("Initializing banknote detection service (loading ML models)...")
        banknote_service = BanknoteStageService(settings)
        logger.info("Initializing Kafka producer...")
        kafka_producer_instance = BanknoteKafkaProducer(settings)
        logger.info("Initializing Kafka consumer...")
        consumer_instance = VideoConsumer(settings)

        if _shutdown_requested:
            logger.info("Shutdown requested during initialization, not consuming")
        else:
            cached_key = None
            cached_result = None

            def process_video_callback(video_data: dict):
                nonlocal cached_key, cached_result
                try:
                    job = PipelineStageEnvelope.model_validate(video_data)
                except ValidationError as e:
                    raise PoisonMessageError(f"Invalid pipeline envelope: {e}") from e

                cache_key = (job.correlation_id, job.video_path)
                if cached_key != cache_key or cached_result is None:
                    cached_result = banknote_service.process(job)
                    cached_key = cache_key
                completion = job.with_completion(
                    StageName.BANKNOTE, cached_result.model_dump()
                )
                sent = kafka_producer_instance.send_stage_result(completion)
                if not sent:
                    raise RuntimeError("Failed to send banknote detection stage result")
                cached_key = None
                cached_result = None

            consumer_instance.consume_videos(process_video_callback)
    except ConsumerFatalError as e:
        logger.error("Consumer failed fatally: %s", e, exc_info=True)
        exit_code = 1
    except RuntimeError as e:
        logger.error("CRITICAL: Service cannot start - %s", e, exc_info=True)
        exit_code = 1
    except Exception as e:
        logger.error("Fatal error in banknote detector service: %s", e, exc_info=True)
        exit_code = 1
    finally:
        if consumer_instance:
            consumer_instance.close()
        if kafka_producer_instance:
            kafka_producer_instance.close()
        logger.info("Banknote detector service stopped")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
