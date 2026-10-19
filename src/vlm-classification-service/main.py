import logging
import signal
import sys

from pydantic import ValidationError

from adapters.kafka_consumer import ConsumerFatalError, PoisonMessageError, VideoConsumer
from adapters.kafka_producer import VlmKafkaProducer
from classification.service import VlmClassificationService
from common.kafka_messages import PipelineStageEnvelope, StageName
from config.settings import settings

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("/app/logs/vlm-classification-service.log"),
    ],
)
logger = logging.getLogger(__name__)

_consumer: VideoConsumer | None = None
_shutdown_requested = False


def signal_handler(signum, frame):
    global _shutdown_requested
    logger.info("Received signal %s, shutting down...", signum)
    _shutdown_requested = True
    if _consumer:
        _consumer.stop()


def main():
    global _consumer
    logger.info("Starting %s v%s", settings.service_name, settings.service_version)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    kafka_producer = None
    exit_code = 0
    try:
        logger.info("Initializing Kafka consumer...")
        _consumer = VideoConsumer(settings)

        logger.info("Initializing Kafka producer...")
        kafka_producer = VlmKafkaProducer(settings)

        logger.info("Initializing VLM classification service (loading model)...")
        classification_service = VlmClassificationService(settings)
        logger.info("VLM classification service initialized successfully")

        if _shutdown_requested:
            logger.info("Shutdown requested during initialization, not consuming")
        else:
            cached_key = None
            cached_result = None

            def process_video_callback(video_data):
                nonlocal cached_key, cached_result
                try:
                    job = PipelineStageEnvelope.model_validate(video_data)
                except ValidationError as e:
                    raise PoisonMessageError(f"Invalid pipeline envelope: {e}") from e

                cache_key = (job.correlation_id, job.video_path)
                if cached_key != cache_key or cached_result is None:
                    cached_result = classification_service.process(job)
                    cached_key = cache_key
                completion = job.with_completion(StageName.VLM, cached_result.model_dump())
                if not kafka_producer.send_stage_result(completion):
                    raise RuntimeError("Failed to send VLM stage result")
                cached_key = None
                cached_result = None

            logger.info("Starting VLM classification service...")
            _consumer.consume_videos(process_video_callback)

    except ConsumerFatalError as e:
        logger.error("Consumer failed fatally: %s", e, exc_info=True)
        exit_code = 1
    except RuntimeError as e:
        logger.error("CRITICAL: Service cannot start - %s", e, exc_info=True)
        exit_code = 1
    except Exception as e:
        logger.error("Fatal error in VLM classification service: %s", e, exc_info=True)
        exit_code = 1
    finally:
        if _consumer:
            _consumer.close()
        if kafka_producer:
            kafka_producer.close()
        logger.info("VLM classification service stopped")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
